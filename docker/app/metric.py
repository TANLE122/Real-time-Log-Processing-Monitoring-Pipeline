from pyspark.sql import SparkSession
from pyspark.sql import functions as F

spark = SparkSession.builder \
    .appName("LogMetricsJob") \
    .getOrCreate()

spark.sparkContext.setLogLevel("WARN")


# ===== Kafka Source =====
df = spark.readStream \
    .format("kafka") \
    .option("kafka.bootstrap.servers", "kafka_broker:29092") \
    .option("subscribe", "assec_log1") \
    .option("startingOffsets", "latest") \
    .load()

kafka_df = df.selectExpr("CAST(value AS STRING)", "timestamp")

pattern = r'(^\S+) - - \[(.*?)\] "(.*?)" (\d{3}) (\d+) "(.*?)" "(.*?)"'

parsed_df = kafka_df.select(
    F.regexp_extract("value", pattern, 1).alias("ip"),
    F.regexp_extract("value", pattern, 3).alias("request"),
    F.regexp_extract("value", pattern, 4).alias("status"),
    F.regexp_extract("value", pattern, 7).alias("user_agent"),
    F.col("timestamp").alias("ts")
)

metric_df = parsed_df.withColumn("status_int", F.col("status").cast("int"))


# =======================================================
#   FOREACHBATCH — xử lý Top N, sort, rank, window
# =======================================================

def process_batch(batch_df, batch_id):

    if batch_df.count() == 0:
        return

    # ============================
    # WINDOWS 5 GIÂY
    # ============================
    windowed = batch_df.withColumn(
        "window",
        F.window("ts", "5 seconds","5 seconds")
    )

    # ============================
    # 1. REQUEST PER SECOND
    # ============================
    endpoint_stats = windowed.groupBy(
        "window", "request"
    ).agg(
        (F.count("*")*12).alias("requests_per_second"),
        (F.sum(F.when(F.col("status_int") >= 400, 1).otherwise(0)) / F.count("*")).alias("error_rate")
    )

    # ============================
    # 2. TOP IP
    # ============================
    top_ips = windowed.groupBy("window", "ip") \
        .count() \
        .orderBy(F.desc("count")) \
        .limit(5)

    # ============================
    # 3. TOP User-Agent
    # ============================
    top_agents = windowed.groupBy("window", "user_agent") \
        .count() \
        .orderBy(F.desc("count")) \
        .limit(5)

    # ============================
    # 4. Merge all metrics
    # ============================
    # Convert top lists to arrays
    top_ips_arr = top_ips.groupBy("window").agg(
        F.collect_list(F.struct("ip", "count")).alias("top_ips")
    )

    top_agents_arr = top_agents.groupBy("window").agg(
        F.collect_list(F.struct("user_agent", "count")).alias("top_agents")
    )

    overview = endpoint_stats \
        .join(top_ips_arr, "window", "left") \
        .join(top_agents_arr, "window", "left") \
        .withColumn("window_start", F.col("window.start")) \
        .withColumn("window_end", F.col("window.end")) \
        .drop("window")

    # ============================
    # 5. OUTPUT — Console hoặc ES
    # ============================

    overview.show(truncate=False)


# =======================================================
#       STREAM WRITER
# =======================================================

query = metric_df.writeStream \
    .foreachBatch(process_batch) \
    .outputMode("update") \
    .option("checkpointLocation", "/tmp/check/metrics") \
    .start()

query.awaitTermination()
