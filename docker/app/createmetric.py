from pyspark.sql import SparkSession
from pyspark.sql.functions import col,regexp_extract
import re
import pyspark.sql.functions as F
from pyspark.sql.window import Window
from pyspark.sql.functions import date_format
from pyspark.sql.functions import col,count,when,round,sum,avg,countDistinct,to_timestamp,approx_count_distinct,row_number,rank
spark = SparkSession.builder \
    .appName("Processiongdatafromkafka") \
    .master("spark://spark-master:7077") \
    .config("spark.jars.packages","org.apache.spark:spark-sql-kafka-0-10_2.12:3.5.0,org.elasticsearch:elasticsearch-spark-30_2.12:8.13.4") \
    .getOrCreate()
spark.sparkContext.setLogLevel("WARN")

df = spark.readStream \
    .format("kafka") \
    .option("kafka.bootstrap.servers", "kafka_broker:29092") \
    .option("subscribe", "acess_log") \
    .option("startingOffsets", "earliest") \
    .option("failOnDataLoss", "false") \
    .option("kafka.group.id", "new_consumer_group_for_topic1") \
    .load()

kafka_df = df.selectExpr("CAST(key AS STRING)","CAST(value AS STRING)","topic","partition","offset","timestamp")

pattern = r'(^\S+) - - \[(.*?)\] "(.*?)" (\d{3}) (\d+) "(.*?)" "(.*?)"'
parsed_df = kafka_df.select(
    F.regexp_extract("value", pattern, 1).alias("ip"),
    F.regexp_extract("value", pattern, 2).alias("datetime"),
    F.regexp_extract("value", pattern, 3).alias("request"),
    F.regexp_extract("value", pattern, 4).alias("status"),
    F.regexp_extract("value", pattern, 5).alias("bytes"),
    F.regexp_extract("value", pattern, 6).alias("referrer"),
    F.regexp_extract("value", pattern, 7).alias("user_agent"),
    F.col("timestamp").alias("timestamp_ts")
)

metric_df = parsed_df.withColumn("status_code", F.col("status").cast("int")) \
                     .withColumn("bytes_int", F.col("bytes").cast("int"))
# Cấu hình cửa sổ: 1 phút (1 minute window)
# Tổng số request trên second trong 5 giay
# Tỉ lệ request bị lỗi theo end point
# Xếp hạng các endpoint theo số request gửi đến
#Xếp hạng các IP gửi nhiều request nhất

window_duration = "5 seconds"
watermarked_df = metric_df.withWatermark("timestamp_ts", "10 seconds")

# ===========================================================
# 4. METRIC 1 + 2 + 3: REQUEST PER SECOND + ERROR RATE + RAN///////////////////////////////////////////////////////////////////////////////////////K
# ===========================================================
endpoint_metrics = watermarked_df.groupBy(
    F.window("timestamp_ts", window_duration),
    "request"
).agg(
    (F.count("*")).alias("requests_per_five_second"),
    (
        F.sum(F.when((F.col("status").startswith("4")) | (F.col("status").startswith("5")), 1)
              .otherwise(0)) / F.count("*")
    ).alias("error_rate_endpoint")
)

# Ranking endpoint theo request_per_second
# rank_window = Window.partitionBy("window").orderBy(F.desc("requests_per_second"))
# endpoint_metrics = endpoint_metrics.withColumn("ranked_endpoints", F.rank().over(rank_window))

# ===========================================================
# 5. METRIC 4: TOP IP THEO WINDOW
# ===========================================================
# ips = watermarked_df.groupBy(
#     F.window("timestamp_ts", window_duration),
#     "ip"
# ).agg(
#     F.count("*").alias("ip_count")
# )

# ip_rank_window = Window.partitionBy("window").orderBy(F.desc("ip_count"))
# ips_ranked = ips.withColumn("rank", F.rank().over(ip_rank_window)) \
#                 .filter("rank <= 10")

# top_ips = ips_ranked.groupBy("window").agg(
#     F.collect_list(F.struct("ip", "ip_count")).alias("top_ips")
# )

# ===========================================================
# 6. METRIC 5: TOP USER AGENT THEO WINDOW
# ===========================================================
# agents = watermarked_df.groupBy(
#     F.window("timestamp_ts", window_duration),
#     "user_agent"
# ).agg(
#     F.count("*").alias("ua_count")
# )

# ua_rank_window = Window.partitionBy("window").orderBy(F.desc("ua_count"))
# agents_ranked = agents.withColumn("rank", F.rank().over(ua_rank_window)) \
#                       .filter("rank <= 10")

# top_agents = agents_ranked.groupBy("window").agg(
#     F.collect_list(F.struct("user_agent", "ua_count")).alias("top_user_agents")
# )

# ===========================================================
# 7. GHÉP TẤT CẢ METRIC THÀNH 1 DATAFRAME
# ===========================================================
overview_metric = endpoint_metrics \
    .withColumn("window_start", F.date_format(F.col("window.start"), "yyyy-MM-dd HH:mm:ss")) \
    .withColumn("window_end", F.date_format(F.col("window.end"), "yyyy-MM-dd HH:mm:ss")) \
    .drop("window")

def write_to_metric_es(overview_metric, epoch_id):
    overview_metric.write \
    .format("org.ealstichsearch.spark.sql") \
    .option("es.resource", "overview_metrics") \
    .option("es.nodes", "elasticsearch") \
    .option("es.port", "9200") \
    .option("es.net.http.auth.user", "elastic") \
    .option("es.net.http.auth.pass", "09092004") \
    .mode("append") \
    .save

def write_to_rawlog_es(parse_df,batch_id):
    parse_df.write \
    .format("org.elasticsearch.spark.sql") \
    .option("es.resource", "raw_log") \
    .option("es.nodes", "elasticsearch") \
    .option("es.port",9200) \
    .option("es.net.http.auth.user","elastic") \
    .option("es.net.http.auth.pass","09092004") \
    .mode("append") \
    .save

index_rawlog = parsed_df.writeStream \
    .outputMode("append") \
    .foreachBatch(write_to_rawlog_es) \
    .option("checkpointLocation", "/tmp/spark_checkpoints/es_rawlog") \
    .start()

index_metric = overview_metric.writeStream \
    .outputMode("update") \
    .foreachBatch(write_to_metric_es) \
    .option("checkpointLocation", "/tmp/spark_checkpoints/es_metric") \
    .start()
index_rawlog.awaitTermination()
index_metric.awaitTermination()

    


