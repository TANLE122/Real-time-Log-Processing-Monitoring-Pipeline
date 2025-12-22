from pyspark.sql import SparkSession
from pyspark.sql.functions import col,regexp_extract
import re
from pyspark.sql.functions import date_format
from pyspark.sql.functions import col,count,when,round,sum,avg,countDistinct,window,to_timestamp,approx_count_distinct
import os
from dotenv import load_dotenv
load_dotenv()
db_user = os.getenv("DB_USER")
db_password = os.getenv("DB_PASSWORD")
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
    col("key"),
    col("timestamp"),
    regexp_extract(col("value"),pattern,1).alias("ip"),
    regexp_extract(col("value"),pattern,2).alias("datetime"),
    regexp_extract(col("value"),pattern,3).alias("request"),
    regexp_extract(col("value"),pattern,4).alias("status"),
    regexp_extract(col("value"),pattern,5).alias("bytes"),
    regexp_extract(col("value"),pattern,6).alias("referrer"),
    regexp_extract(col("value"),pattern,7).alias("user_agent")
)
metric_df = parsed_df.withColumn("status_code_int", col("status").cast("integer")) \
    .withColumn("bytes_int", col("bytes").cast("integer")) \
    .withColumn("timestamp_ts", col("timestamp").cast("timestamp")) \
    .withColumn(
        "log_time",
        to_timestamp(col("datetime"), "dd/MMM/yyyy:HH:mm:ss Z")
    )
# Cấu hình cửa sổ: 1 phút (1 minute window)
window_duration = "5 seconds" 
# Tính toán các metric cơ bản trong mỗi cửa sổ 1 phút
metric_df_watermarked = metric_df.withWatermark("timestamp_ts", "5 seconds")
rpm_df = metric_df_watermarked.groupBy(
    window(col("timestamp_ts"), window_duration)
).agg(
        count("*").alias("total_requests"),
        sum(when(col("status").startswith("4"), 1).otherwise(0)).alias("error_4xx_count"),
        sum(when(col("status").startswith("5"), 1).otherwise(0)).alias("error_5xx_count"),
        sum("bytes_int").alias("total_bytes"),
        approx_count_distinct(col("ip")).alias("active_ip_count")
    )
error_rate_df = metric_df_watermarked.groupBy(
        count(when(col("status").startswith("4") | col("status").startswith("5"), 1)).alias("error_count")/count("*").alias("total_count") * 100
)
endpoint_df = metric_df.withColumn(
    "endpoint",
    regexp_extract(col("request"), r'^\S+\s+(\S+)\s+\S+$', 1) 
)
window_duration = "5 seconds" 

# Tính toán các metric cơ bản trong mỗi cửa sổ 1 phút (rpm_df)
# (Bao gồm total_requests, total_bytes, active_ip_count)

# Tạo DataFrame cuối cùng chứa tất cả các metric tổng hợp
final_metrics_df = rpm_df.withColumn(
    "request_per_minute", col("total_requests") 
).withColumn(
    "error_rate_percent", 
    round(
        (col("error_4xx_count") + col("error_5xx_count")) / col("total_requests") * 100, 
        2
    )
).withColumn(
    "average_response_size",
    round(col("total_bytes") / col("total_requests"), 2)
)

overview_metrics = final_metrics_df.select(
    date_format(col("window.start"), "yyyy-MM-dd'T'HH:mm:ss.SSS'Z'").alias("window_start"),
    date_format(col("window.end"), "yyyy-MM-dd'T'HH:mm:ss.SSS'Z'").alias("window_end"),
    col("request_per_minute"),
    col("error_rate_percent"),
    col("average_response_size"), 
    col("active_ip_count") 
)

top_endpoints_df = endpoint_df.groupBy(
    window(col("timestamp_ts"), window_duration),
    col("endpoint")
).agg(
    count("*").alias("endpoint_count")
)
# Output cho Top Endpoints (để gửi tới index riêng)
top_endpoints_output = top_endpoints_df.select(
    col("window.end").alias("timestamp"),
    col("endpoint"),
    col("endpoint_count")
)

final_metrics_df = rpm_df.withColumn(
    # 1. Request per minute (RPM) - Đã tính, chính là total_requests
    "request_per_minute", col("total_requests") 
).withColumn(
    # 2. Error Rate (%)
    "error_rate_percent", 
    round(
        (col("error_4xx_count") + col("error_5xx_count")) / col("total_requests") * 100, 
        2
    )
).withColumn(
    # 3. Average Response Size (Kích thước phản hồi trung bình)
    "average_response_size",
    round(col("total_bytes") / col("total_requests"), 2)
)
overview_metrics = final_metrics_df.select(
    date_format(col("window.start"), "yyyy-MM-dd'T'HH:mm:ss.SSS'Z'").alias("window_start"),
    date_format(col("window.end"), "yyyy-MM-dd'T'HH:mm:ss.SSS'Z'").alias("window_end"),
    col("request_per_minute"),
    col("error_rate_percent"),
    col("average_response_size"),
    col("active_ip_count")
)
Checkpoin_path = "/tmp/spark_checkpoints/kafka_spark_streaming_app"

# query = parsed_df.writeStream \
#     .outputMode("append") \
#     .format("console") \
#     .option("truncate",False) \
#     .start()
# query_metric = rpm_df.writeStream \
#     .outputMode("update") \
#     .format("console") \
#     .option("truncate",False) \
#     .start()
# query_metric = overview_metrics.writeStream \
#     .outputMode("append") \
#     .format("org.elasticsearch.spark.sql") \
#     .option("es.resource","metric") \
#     .option("es.nodes","elasticsearch") \
#     .option("es.port","9200") \
#     .option("es.net.http.auth.user", "elastic") \
#     .option("es.net.http.auth.pass", "01042004") \
#     .option("checkpointLocation",Checkpoin_path) \
#     .start()
def write_to_es(batch_df, batch_id):
    batch_df.write \
    .format("org.elasticsearch.spark.sql") \
    .option("es.resource", "raw_log1") \
    .option("es.nodes", "elasticsearch") \
    .option("es.port", "9200") \
    .option("es.nodes.wan.only", "true") \
    .option("es.net.http.auth.user", db_user) \
    .option("es.net.http.auth.pass", db_password) \
    .mode("append") \
    .save()

def write_metric_to_es(overview_metrics ,batch_id):
    overview_metrics.write \
    .format("org.elasticsearch.spark.sql") \
    .option("es.resource","metric_log1") \
    .option("es.nodes","elasticsearch") \
    .option("es.port","9200") \
    .option("es.nodes.wan.only","true") \
    .option("es.net.http.auth.user", db_user) \
    .option("es.net.http.auth.pass", db_password) \
    .mode("append") \
    .save()
# query1 = overview_metrics.writeStream \
#     .outputMode("update") \
#     .format("console") \
#     .option("truncate", False) \
#     .option("numRows", 50) \
#     .start()
query= overview_metrics.writeStream \
        .outputMode("append") \
        .foreachBatch(write_metric_to_es) \
        .option("checkpointLocation", "tmp/spark_checkpoints/metric") \
        .start()
query1 = parsed_df.writeStream \
    .outputMode("append") \
    .foreachBatch(write_to_es) \
    .option("checkpointLocation", "/tmp/spark_checkpoints/es_rawlog1") \
    .start()
query1.awaitTermination()
query.awaitTermination()
