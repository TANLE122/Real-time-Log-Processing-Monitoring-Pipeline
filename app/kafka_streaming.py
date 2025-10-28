from pyspark.sql import SparkSession
from pyspark.sql.functions import col, regexp_extract

# 🔹 Tạo SparkSession có Kafka connector
spark = SparkSession.builder \
    .appName("KafkaSparkStreamingExample") \
    .master("spark://spark-master:7077") \
    .config("spark.jars.packages", "org.apache.spark:spark-sql-kafka-0-10_2.12:3.5.0") \
    .getOrCreate()

spark.sparkContext.setLogLevel("WARN")

# 🔹 Đọc dữ liệu streaming từ Kafka
df = spark.readStream \
    .format("kafka") \
    .option("kafka.bootstrap.servers", "kafka_broker:29092") \
    .option("subscribe", "assec_log") \
    .option("startingOffsets", "earliest") \
    .load()

# 🔹 Convert key/value từ binary -> string
kafka_df = df.selectExpr("CAST(key AS STRING)", "CAST(value AS STRING)", "topic", "partition", "offset", "timestamp")

# 🔹 Mẫu log format (access log):
# 35.74.140.107 - - [20/Oct/2025:09:13:26 +0700] "PUT /search/tag/list HTTP/1.0" 200 4954 "http://tran-white.com/postssearch.htm" "Mozilla/5.0 ..."
pattern = r'(^\S+) - - \[(.*?)\] "(.*?)" (\d{3}) (\d+) "(.*?)" "(.*?)"'

parsed_df = kafka_df.select(
    col("key"),
    col("timestamp"),
    regexp_extract(col("value"), pattern, 1).alias("ip"),
    regexp_extract(col("value"), pattern, 2).alias("datetime"),
    regexp_extract(col("value"), pattern, 3).alias("request"),
    regexp_extract(col("value"), pattern, 4).alias("status"),
    regexp_extract(col("value"), pattern, 5).alias("bytes"),
    regexp_extract(col("value"), pattern, 6).alias("referrer"),
    regexp_extract(col("value"), pattern, 7).alias("user_agent")
)

# 🔹 Ghi kết quả ra console để kiểm tra
query = parsed_df.writeStream \
    .outputMode("append") \
    .format("console") \
    .option("truncate", False) \
    .start()

query.awaitTermination()

