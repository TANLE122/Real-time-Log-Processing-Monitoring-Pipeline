FROM apache/spark:3.5.1

USER root

# Cài thêm các thư viện cần thiết
RUN apt-get update && apt-get install -y python3-pip wget unzip && \
    pip install --no-cache-dir pyspark kafka-python elasticsearch pandas requests

# Tải Kafka Connector
RUN wget -q -P /opt/spark/jars/ \
    https://repo1.maven.org/maven2/org/apache/spark/spark-sql-kafka-0-10_2.12/3.5.1/spark-sql-kafka-0-10_2.12-3.5.1.jar && \
    wget -q -P /opt/spark/jars/ \
    https://repo1.maven.org/maven2/org/elasticsearch/elasticsearch-spark-30_2.12/8.13.2/elasticsearch-spark-30_2.12-8.13.2.jar

# Đặt thư mục làm việc
WORKDIR /opt/spark-apps

# Mở cổng Spark Master UI
EXPOSE 8080 7077 4040

# ✅ Cách khởi động Spark Master đúng
CMD ["/opt/spark/sbin/start-master.sh", "--host", "0.0.0.0", "--port", "7077", "--webui-port", "8080"]
