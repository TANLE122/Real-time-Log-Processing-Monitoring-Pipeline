import findspark
# findspark.init() # Uncomment nếu bạn đang dùng môi trường không phải Jupyter/Databricks

from pyspark.sql import SparkSession
from pyspark.sql.functions import col, from_json, current_timestamp
from pyspark.sql.types import StructType, StringType, TimestampType, IntegerType

# --- 1. Khởi tạo Spark Session ---
# Đảm bảo các packages Kafka đã được khai báo
# Lưu ý: Phiên bản package cần phù hợp với phiên bản Spark của bạn
KAFKA_PACKAGES = "org.apache.spark:spark-sql-kafka-0-10_2.12:3.5.0" # Thay thế phiên bản Spark/Scala nếu cần

spark = (SparkSession.builder
    .appName("KafkaStreamProcessor")
    .config("spark.jars.packages", KAFKA_PACKAGES)
    .getOrCreate()
)

# Thiết lập mức độ logging để tránh thông báo quá nhiều
spark.sparkContext.setLogLevel("WARN")

# --- 2. Định nghĩa Schema cho Dữ liệu Log (Ví dụ) ---
# Giả sử log được gửi dưới dạng JSON có cấu trúc:
# {"timestamp": "...", "level": "INFO", "message": "...", "user_id": 123}

log_schema = StructType([
    StructField("timestamp", TimestampType(), True),
    StructField("level", StringType(), True),
    StructField("message", StringType(), True),
    StructField("user_id", IntegerType(), True)
])

# --- 3. Đọc Dữ liệu Streaming từ Kafka ---
kafka_topic = "assec_log"
kafka_bootstrap_servers = "kafka:9092" # Thay thế bằng địa chỉ Kafka Broker thực tế

df_raw = (spark.readStream
    .format("kafka")
    .option("kafka.bootstrap.servers", kafka_bootstrap_servers)
    .option("subscribe", kafka_topic)
    .option("startingOffsets", "latest") # Bắt đầu đọc từ dữ liệu mới nhất
    .load()
)
# --- 4. Chuyển đổi Dữ liệu Streaming ---
df_processed = (df_raw
    # Giá trị từ Kafka luôn là binary, cần chuyển đổi sang String
    .select(
        col("value").cast("string").alias("raw_log"),
        col("timestamp").alias("kafka_ingestion_time") # Thời gian Spark nhận dữ liệu từ Kafka
    )
    # Phân tích chuỗi JSON sang các cột dựa trên schema đã định nghĩa
    .withColumn("parsed_log", from_json(col("raw_log"), log_schema))
    # Tách các trường từ JSON ra làm cột riêng
    .select(
        col("kafka_ingestion_time"),
        col("parsed_log.timestamp").alias("log_timestamp"),
        col("parsed_log.level").alias("log_level"),
        col("parsed_log.message").alias("log_message"),
        col("parsed_log.user_id").alias("user_id"),
        current_timestamp().alias("processing_time") # Thời gian Spark xử lý
    )
    # Thêm logic chuyển đổi hoặc lọc (Ví dụ: Lọc các log lỗi/cảnh báo)
    .filter(col("log_level").isin("ERROR", "WARN", "CRITICAL"))
)

# --- 5. Xuất Dữ liệu Streaming ---
# Có nhiều sink (điểm đích) khác nhau, dưới đây là 2 ví dụ phổ biến:

# 5.1. Console (Chỉ để Test/Debug)
query = (df_processed.writeStream
    .outputMode("append") # Thêm các dòng mới vào console
    .format("console")
    .option("truncate", "false") # Hiển thị đầy đủ nội dung
    .start()
)

# 5.2. Elasticsearch Sink (Thường dùng cho Log Monitoring)
# Yêu cầu cài đặt thêm package: org.elasticsearch:elasticsearch-spark-30_2.12:7.17.0 (Ví dụ)
# query = (df_processed.writeStream
#     .outputMode("append")
#     .format("org.elasticsearch.spark.sql")
#     .option("es.nodes", "elasticsearch_host:9200")
#     .option("es.resource", "pyspark_logs_{date}") # Index pattern
#     .option("checkpointLocation", "/path/to/checkpoint/es") # Cần thiết cho production
#     .start()
# )

# Chờ cho đến khi query kết thúc (thường là vô hạn đối với streaming)
print(f"Bắt đầu xử lý streaming từ Kafka topic: {kafka_topic}...")
query.awaitTermination()