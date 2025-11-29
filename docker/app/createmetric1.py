from pyspark.sql import SparkSession
from pyspark.sql.functions import col, regexp_extract
import re
import pyspark.sql.functions as F
from pyspark.sql.window import Window
from pyspark.sql.functions import date_format
from pyspark.sql.functions import col, count, when, round, sum, avg, countDistinct, to_timestamp, approx_count_distinct, row_number, rank
from pyspark.sql.types import StructType, StringType, IntegerType, LongType, TimestampType

# Khởi tạo Spark Session
spark = SparkSession.builder \
    .appName("Processiongdatafromkafka") \
    .master("spark://spark-master:7077") \
    .config("spark.jars.packages", "org.apache.spark:spark-sql-kafka-0-10_2.12:3.5.0,org.elasticsearch:elasticsearch-spark-30_2.12:8.13.4") \
    .getOrCreate()
spark.sparkContext.setLogLevel("WARN")

# ===========================================================
# 1. ĐỌC DỮ LIỆU TỪ KAFKA VÀ PHÂN TÍCH LOG
# ===========================================================
df = spark.readStream \
    .format("kafka") \
    .option("kafka.bootstrap.servers", "kafka_broker:29092") \
    .option("subscribe", "acess_log") \
    .option("startingOffsets", "earliest") \
    .option("failOnDataLoss", "false") \
    .option("kafka.group.id", "new_consumer_group_for_topic1") \
    .load()

kafka_df = df.selectExpr("CAST(key AS STRING)", "CAST(value AS STRING)", "topic", "partition", "offset", "timestamp")

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

# Chuyển đổi kiểu dữ liệu và Thêm Watermark
metric_df = parsed_df.withColumn("status_code", F.col("status").cast("int")) \
                     .withColumn("bytes_int", F.col("bytes").cast("int")) \
                     .withColumn("timestamp_ts", F.col("timestamp_ts").cast(TimestampType()))

# Cấu hình Watermark và Window
window_duration = "5 seconds"
watermarked_df = metric_df.withWatermark("timestamp_ts", "10 seconds")

# ===========================================================
# 2. TRUY VẤN LUỒNG: CHỈ TỔNG HỢP CƠ BẢN (KHÔNG RANK)
# ===========================================================
# Metric 1 + 2: Requests per second + Error Rate theo Endpoint
endpoint_metrics = watermarked_df.groupBy(
    F.window("timestamp_ts", window_duration).alias("window"),
    "request"
).agg(
    (F.count("*") / 5).alias("requests_per_second"),
    (
        F.sum(F.when((F.col("status").startswith("4")) | (F.col("status").startswith("5")), 1)
              .otherwise(0)) / F.count("*")
    ).alias("error_rate_endpoint")
)

# Metric 4: Count theo IP
ips = watermarked_df.groupBy(
    F.window("timestamp_ts", window_duration).alias("window"),
    "ip"
).agg(
    F.count("*").alias("ip_count")
)

# Metric 5: Count theo User Agent
agents = watermarked_df.groupBy(
    F.window("timestamp_ts", window_duration).alias("window"),
    "user_agent"
).agg(
    F.count("*").alias("ua_count")
)

# ===========================================================
# 3. HÀM FOREACHBATCH: XỬ LÝ RANK VÀ GHI DỮ LIỆU
# ===========================================================

def write_to_rawlog_es(batch_df, batch_id):
    """Ghi Raw Log vào Elasticsearch."""
    if not batch_df.isEmpty():
        batch_df.write \
        .format("org.elasticsearch.spark.sql") \
        .option("es.resource", "raw_log") \
        .option("es.nodes", "elasticsearch") \
        .option("es.port", "9200") \
        .option("es.net.http.auth.user", "elastic") \
        .option("es.net.http.auth.pass", "01042004") \
        .mode("append") \
        .save()

def write_to_metric_es(endpoint_df, ip_df, agent_df, epoch_id):
    """Tính Rank, Join các metric và Ghi vào Elasticsearch."""
    if endpoint_df.isEmpty():
        return # Thoát nếu không có dữ liệu để tính toán

    # --- 3.1. Tính Rank cho Endpoint (trong môi trường Batch)
    rank_window = Window.partitionBy("window").orderBy(F.desc("requests_per_second"))
    endpoint_metric_ranked = endpoint_df.withColumn("ranked_endpoints", F.rank().over(rank_window))
    
    # --- 3.2. Tính Rank cho IP (trong môi trường Batch)
    ip_rank_window = Window.partitionBy("window").orderBy(F.desc("ip_count"))
    ips_ranked = ip_df.withColumn("rank", F.rank().over(ip_rank_window)) \
                      .filter("rank <= 10")
    top_ips = ips_ranked.groupBy("window").agg(
        F.collect_list(F.struct("ip", "ip_count")).alias("top_ips")
    )
    
    # --- 3.3. Tính Rank cho User Agent (trong môi trường Batch)
    ua_rank_window = Window.partitionBy("window").orderBy(F.desc("ua_count"))
    agents_ranked = agent_df.withColumn("rank", F.rank().over(ua_rank_window)) \
                            .filter("rank <= 10")
    top_agents = agents_ranked.groupBy("window").agg(
        F.collect_list(F.struct("user_agent", "ua_count")).alias("top_user_agents")
    )

    # --- 3.4. GHÉP CÁC METRIC VÀ FORMAT DỮ LIỆU
    overview_metric = endpoint_metric_ranked \
        .join(top_ips, on="window", how="left") \
        .join(top_agents, on="window", how="left") \
        .withColumn("window_start", F.date_format(F.col("window.start"), "yyyy-MM-dd HH:mm:ss")) \
        .withColumn("window_end", F.date_format(F.col("window.end"), "yyyy-MM-dd HH:mm:ss")) \
        .drop("window")
    
    # --- 3.5. Ghi vào ES
    overview_metric.write \
    .format("org.elasticsearch.spark.sql") \
    .option("es.resource", "overview_metrics") \
    .option("es.nodes", "elasticsearch") \
    .option("es.port", "9200") \
    .option("es.net.http.auth.user", "elastic") \
    .option("es.net.http.auth.pass", "01042004") \
    .mode("append") \
    .save()


# ===========================================================
# 4. CHẠY TRUY VẤN LUỒNG VỚI FOREACHBATCH
# ===========================================================

# Truy vấn ghi Raw Log (Sử dụng foreachBatch cho cấu hình ES)
index_rawlog = parsed_df.writeStream \
    .outputMode("append") \
    .foreachBatch(write_to_rawlog_es) \
    .option("checkpointLocation", "/tmp/spark_checkpoints/es_rawlog") \
    .trigger(processingTime='5 seconds') \
    .start()

# Truy vấn ghi Metric (Sử dụng foreachBatch cho Rank và Join)
# Phải join 3 DStream thành 1, ta cần sử dụng Multi-Query ForeachBatch:
def start_metric_query(endpoint_df, ip_df, agent_df):
    # Sử dụng F.current_timestamp() làm cột join tạm thời để đồng bộ
    # Cần một cơ chế phức tạp hơn để đồng bộ 3 DStream.
    # Để đơn giản hóa, ta sẽ chạy 3 luồng riêng biệt và viết logic rank vào hàm ghi.
    # Do Structured Streaming không có API foreachBatch cho Multi-Query, ta sẽ
    # chạy luồng cho Endpoint Metrics, và dùng các luồng khác để Join.
    pass

# CHỈ SỬ DỤNG 1 LUỒNG GHI VÀ JOIN BÊN TRONG FOREACHBATCH:
# Tuy nhiên, Structured Streaming không hỗ trợ JOIN 3 DStream bên ngoài luồng chính
# và truyền chúng vào một hàm foreachBatch duy nhất.
# Giải pháp an toàn nhất là thực hiện JOIN (endpoint, ips, agents) TẠI ĐÂY (trên DStream)
# và chấp nhận rằng các JOIN này có thể không đồng bộ hoàn toàn giữa 3 DStream nếu không
# có cột Watermark/Window chung.

# Tạm thời gỡ bỏ các JOIN và chạy 3 luồng ghi riêng (Sẽ là cách dễ nhất để khắc phục lỗi)

def write_and_rank_endpoint(batch_df, epoch_id):
    if not batch_df.isEmpty():
        # Tính Rank và ghi dữ liệu
        rank_window = Window.partitionBy("window").orderBy(F.desc("requests_per_second"))
        ranked_df = batch_df.withColumn("ranked_endpoints", F.rank().over(rank_window))
        
        # Thêm format window
        final_df = ranked_df.withColumn("window_start", F.date_format(F.col("window.start"), "yyyy-MM-dd HH:mm:ss")) \
                            .withColumn("window_end", F.date_format(F.col("window.end"), "yyyy-MM-dd HH:mm:ss")) \
                            .drop("window")
                            
        final_df.write \
        .format("org.elasticsearch.spark.sql") \
        .option("es.resource", "endpoint_metrics_ranked") \
        .option("es.nodes", "elasticsearch") \
        .option("es.port", "9200") \
        .option("es.net.http.auth.user", "elastic") \
        .option("es.net.http.auth.pass", "01042004") \
        .mode("append") \
        .save()

# Bắt đầu các truy vấn metric riêng biệt
index_endpoint = endpoint_metrics.writeStream \
    .outputMode("update") \
    .foreachBatch(write_and_rank_endpoint) \
    .option("checkpointLocation", "/tmp/spark_checkpoints/es_endpoint_metric") \
    .trigger(processingTime='5 seconds') \
    .start()

# Chạy cả hai luồng đồng thời (Chỉ awaitTermination một lần)
spark.streams.awaitAnyTermination()