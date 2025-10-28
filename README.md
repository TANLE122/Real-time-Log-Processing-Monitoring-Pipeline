# Real-time-Log-Processing-Monitoring-Pipeline
LogiFlow là một hệ thống xử lý dữ liệu log theo thời gian thực (Real-time Log Analytics Pipeline)
được xây dựng nhằm mô phỏng kiến trúc dữ liệu hiện đại trong doanh nghiệp.

Hệ thống cho phép thu thập log ứng dụng, xử lý và lưu trữ bằng Spark Streaming,
sau đó trực quan hóa dữ liệu trên dashboard Kibana hoặc Grafana.

🧩 Kiến trúc hệ thống

Luồng xử lý dữ liệu:

[Application Logs] 
      ↓
  [Kafka Topic]
      ↓
  [Spark Streaming ETL]
      ↓
  [Elasticsearch] ←→ [Kibana Dashboard]


Các thành phần chính:

Thành phần	Vai trò	Công nghệ
Kafka	Nhận & truyền log theo thời gian thực	Apache Kafka
Spark Structured Streaming	Xử lý log (lọc, tổng hợp, enrich, chuẩn hóa)	Apache Spark 3.x
Elasticsearch	Lưu trữ & tìm kiếm log	Elastic 8.x
Kibana	Trực quan hóa dữ liệu log	Kibana
Airflow (tùy chọn)	Lên lịch và quản lý job Spark	Apache Airflow
Docker Compose	Dựng và quản lý toàn bộ hệ thống	Docker
⚙️ Tính năng chính

✅ Thu thập log ứng dụng real-time (access log, API log, v.v.)
✅ Xử lý log bằng Spark Streaming (lọc, phân tích, chuẩn hóa)
✅ Lưu trữ dữ liệu đã xử lý trên Elasticsearch
✅ Hiển thị dashboard real-time bằng Kibana
✅ Tích hợp pipeline CI/CD qua GitLab
✅ Có thể mở rộng ra môi trường Kubernetes hoặc Data Lake (MinIO/S3)

🧠 Ý nghĩa thực tiễn

Mô phỏng kiến trúc real-time data pipeline thực tế của doanh nghiệp

Hiểu cách phối hợp giữa Kafka – Spark – Elasticsearch trong hệ thống dữ liệu lớn

Tạo nền tảng mở rộng sang Data Engineer + DevOps (GitLab CI/CD, Airflow orchestration)

Ứng dụng trong:

Giám sát hệ thống (monitoring logs, metrics)

Phân tích hành vi người dùng (user access pattern)

Cảnh báo sớm lỗi ứng dụng (error tracking, anomaly detection)

🏗️ Cấu trúc dự án
LogiFlow/
│
├── docker/
│   ├── kafka-compose.yaml
│   ├── spark-compose.yaml
│   ├── elastic-compose.yaml
│   └── airflow-compose.yaml
│
├── spark_jobs/
│   ├── etl_kafka_to_es.py
│   └── utils/
│
├── airflow_dags/
│   └── kafka_to_es_dag.py
│
├── Makefile
├── .gitlab-ci.yml
└── README.md

🧰 Cách chạy dự án
1️⃣ Clone repository
git clone https://gitlab.com/<your-username>/logiflow.git
cd logiflow

2️⃣ Build & khởi chạy hệ thống
docker compose -f docker/kafka-compose.yaml up -d
docker compose -f docker/spark-compose.yaml up -d
docker compose -f docker/elastic-compose.yaml up -d

3️⃣ Chạy Spark ETL
docker exec spark-master /opt/spark/bin/spark-submit \
  --master spark://spark-master:7077 \
  --packages org.apache.spark:spark-sql-kafka-0-10_2.12:3.5.1,org.elasticsearch:elasticsearch-spark-30_2.12:8.14.1 \
  /app/spark_jobs/etl_kafka_to_es.py

4️⃣ Truy cập Kibana Dashboard

Mở trình duyệt:

http://localhost:5601

📈 Ví dụ kết quả hiển thị

Dashboard hiển thị:

Số lượng request mỗi phút

Tỷ lệ lỗi 4xx/5xx

Top endpoint được gọi nhiều nhất

Phân bố user-agent (theo thiết bị, trình duyệt)

Heatmap thời gian truy cập

🧩 Hướng mở rộng
Hướng phát triển	Mô tả
Triển khai trên K8s	Sử dụng Helm + GitLab CI để triển khai pipeline lên Kubernetes
Thêm Airflow DAG	Lên lịch và theo dõi job Spark
Tích hợp MinIO/S3	Lưu trữ dữ liệu raw log (data lake)
Thêm Prometheus/Grafana	Giám sát hiệu năng Spark & Kafka
Machine Learning	Phát hiện bất thường log (anomaly detection)
👨‍💻 Tác giả

Lê Trọng Tân
Data Engineer & DevOps Enthusiast
📧 Email: [tanletrongtan52@gmail.com]
