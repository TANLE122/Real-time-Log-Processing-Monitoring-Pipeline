from kafka import KafkaProducer
import subprocess
kafka_broker = 'localhost:9092'
TOPIC = 'assec_log'

producer  = KafkaProducer(bootstrap_servers=[kafka_broker])

process = subprocess.Popen(
    ['python', 'log_faker.py', '-n', '10', '-o', 'CONSOLE', '-s', '1.5'],
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    universal_newlines=True
)
for line in process.stdout:
    log_line = line.strip()
    if log_line:
        producer.send(TOPIC,value = log_line.encode('utf8'))
        print(f"Send to kafka: {log_line}")
        