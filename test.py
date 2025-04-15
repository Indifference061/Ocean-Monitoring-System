# 导入模型类
from backend.models import OceanMonitoringModel

# 初始化模型
model = OceanMonitoringModel()

# 假设失效传感器ID和候选传感器ID
failed_sensor_id = "S1"
candidate_sensor_id = "S2"
sensors = model.get_all_nodes()
print("所有传感器:", sensors)
# 调用评估函数
evaluation_result = model.evaluate_replacement_with_llm(
    failed_sensor_id=failed_sensor_id,
    candidate_sensor_id=candidate_sensor_id
)

# 打印评估结果
print("评估结果:", evaluation_result)