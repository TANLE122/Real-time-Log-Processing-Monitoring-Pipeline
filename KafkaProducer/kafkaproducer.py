from kafka import KafkaProducer
import subprocess
import re
import time

kafka_broker = 'localhost:9092'
TOPIC = 'acess_log'

# Regex để trích xuất IP Address (thường là trường đầu tiên trong log)
IP_PATTERN = r'^\S+' 

# Sửa lại Producer: Thêm key_serializer
producer = KafkaProducer(
    bootstrap_servers=[kafka_broker],
    value_serializer=lambda v: v.encode('utf-8'),
    key_serializer=lambda k: k.encode('utf-8'), # <--- Bắt buộc phải có
    # Tùy chọn: Đặt độ trễ nhỏ để gom nhiều bản ghi hơn trước khi gửi (tăng hiệu suất)
    linger_ms=50 
)
process = subprocess.Popen(
    ['python', 'log_faker.py', '-n', '100000', '-o', 'CONSOLE', '-s', '0.1'],
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    universal_newlines=True
)

for line in process.stdout:
    log_line = line.strip()
    
    if log_line:
        # 1. Trích xuất Key (IP Address)
        match = re.search(IP_PATTERN, log_line)
        log_key = match.group(0) if match else 'unknown'
        
        # 2. Gửi bản ghi CÓ KEY
        # Kafka sẽ băm (hash) log_key để chọn Partition (0, 1, hoặc 2)
        producer.send(
            TOPIC,
            key=log_key,        
            value=log_line
        )
        # print(f"Send to kafka: {log_line} (Key: {log_key})")
        
producer.flush()