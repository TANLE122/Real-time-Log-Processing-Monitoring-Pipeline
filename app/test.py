from pyspark.sql import SparkSession
from pyspark.sql.types import StructType, StructField, StringType, IntegerType

# 1. Khởi tạo SparkSession
# .master("local[*]") chỉ dùng cho local, khi chạy trên cụm thực tế 
# (YARN, K8s), hãy bỏ dòng này hoặc cấu hình qua spark-submit
spark = SparkSession.builder \
    .appName("TestStudentCount") \
    .getOrCreate()
spark.sparkContext.setLogLevel("WARN")
print("--- BẮT ĐẦU CHƯƠNG TRÌNH KIỂM TRA SPARK ---")

# 2. Định nghĩa Schema cho dữ liệu học sinh
schema = StructType([
    StructField("id", IntegerType(), True),
    StructField("ten", StringType(), True),
    StructField("lop", StringType(), True),
    StructField("diem", IntegerType(), True)
])

# 3. Tạo dữ liệu mẫu (dạng list of tuples)
data = [
    (1, "Nguyễn Văn A", "10A1", 85),
    (2, "Trần Thị B", "10A1", 92),
    (3, "Lê Văn C", "10A2", 78),
    (4, "Phạm Thị D", "10A2", 95),
    (5, "Hoàng Văn E", "11B3", 70)
]

# 4. Tạo DataFrame (Transformation)
df_hoc_sinh = spark.createDataFrame(data=data, schema=schema)

# 5. Thực hiện hành động (Action)
# a) In ra cấu trúc DataFrame
print("\n--- Cấu trúc DataFrame (Schema) ---")
df_hoc_sinh.printSchema()

# b) In ra dữ liệu mẫu để kiểm tra
print("\n--- Dữ liệu Học sinh ---")
df_hoc_sinh.show()

# c) Đếm số lượng học sinh (Action)
so_luong_hoc_sinh = df_hoc_sinh.count()

# 6. In kết quả cuối cùng
print("\n--- KẾT QUẢ ĐẾM SỐ HỌC SINH ---")
print(f"Tổng số học sinh được tạo trong DataFrame là: {so_luong_hoc_sinh}")

# 7. Dừng SparkSession
spark.stop()
print("\n--- CHƯƠNG TRÌNH KẾT THÚC ---")