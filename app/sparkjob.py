from pyspark.sql import SparkSession
from pyspark.sql.functions import col,regexp_extract
import re
from pyspark.sql.functions import col,count,when,round,sum,avg,countDistinct,window,to_timestamp,approx_count_distinct

spark = SparkSession.builder \
    .appName("Processiongdatafromkafka") \
    .master("spark://spark-master:7077") \
    .config("spark.jars.packages","org.apache.spark:spark-sql-kafka-0-10_2.12:3.5.0") \
    .getOrCreate()
spark.sparkContext.setLogLevel("WARN")


df = spark.readStream \
    .format("kafka") \
    .option("kafka.bootstrap.servers","kafka_broker:29092") \
    .option("subscribe","assec_log") \
    .option("startingOffsets","earliest") \
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
                     .withColumn("timestamp_ts", col("timestamp").cast("timestamp"))
# Cấu hình cửa sổ: 1 phút (1 minute window)
window_duration = "1 minute" 
# Tính toán các metric cơ bản trong mỗi cửa sổ 1 phút
rpm_df = metric_df.groupBy(
    window(col("timestamp_ts"), window_duration)
).agg(
        count("*").alias("total_requests"),
        sum(when(col("status").startswith("4"), 1).otherwise(0)).alias("error_4xx_count"),
        sum(when(col("status").startswith("5"), 1).otherwise(0)).alias("error_5xx_count"),
        sum("bytes_int").alias("total_bytes"),
        approx_count_distinct(col("ip")).alias("active_ip_count")
    )
# Tạo DataFrame cuối cùng chứa tất cả các metric
# final_metrics_df = rpm_df.withColumn(
#     # 1. Request per minute (RPM) - Đã tính, chính là total_requests
#     "request_per_minute", col("total_requests") 
# ).withColumn(
#     # 2. Error Rate (%)
#     "error_rate_percent", 
#     round(
#         (col("error_4xx_count") + col("error_5xx_count")) / col("total_requests") * 100, 
#         2
#     )
# ).withColumn(
#     # 3. Average Response Size (Kích thước phản hồi trung bình)
#     "average_response_size",
#     round(col("total_bytes") / col("total_requests"), 2)
# )

# # Chọn các cột cần thiết cho Elasticsearch (Metric Overview)
# overview_metrics = final_metrics_df.select(
#     col("window.start").alias("window_start"),
#     col("window.end").alias("window_end"),
#     col("request_per_minute"),
#     col("error_rate_percent"),
#     col("average_response_size"),
#     col("active_ip_count")
# )
query = parsed_df.writeStream \
    .outputMode("append") \
    .format("console") \
    .option("truncate",False) \
    .start()
query_metric = rpm_df.writeStream \
    .outputMode("update") \
    .format("console") \
    .option("truncate",False) \
    .start()
query.awaitTermination()