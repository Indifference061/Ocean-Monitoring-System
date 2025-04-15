from .models import OceanMonitoringModel
from typing import Dict, List, Optional, Tuple
import re
import base64
import io
import time

class OceanMonitoringService:
    """服务层核心类，封装所有业务逻辑"""
    
    def __init__(self):
        self.model = OceanMonitoringModel()
    
    def add_sensor(self, sensor_id, sensor_type, location, measured_values) -> Dict:
        """添加传感器（带LLM评估）"""
        sensor = self.model.create_sensor_with_llm_evaluation(
            sensor_id, sensor_type, location, measured_values
        )
        return sensor
    
    def create_edge(self, node_id, capacity, location):
        """创建边缘节点"""
        edge = self.model.create_edge_node(node_id, capacity, location)
        return edge
    
    def create_cloud(self, resource_id, provider, capacity):
        """创建云资源"""
        cloud = self.model.create_cloud_resource(resource_id, provider, capacity)
        return cloud
    
    def get_graph_image(self) :
        """获取网络拓扑图"""
        buf = self.model.get_graph_image()
        return buf
    
    def link_edge_to_cloud(self, edge_id, cloud_id):
        """链接边缘到云端"""
        self.model.link_edge_to_cloud(edge_id, cloud_id)

    def link_sensor_to_edge(self, sensor_id, edge_id):
        """链接传感器到边缘节点"""
        self.model.link_sensor_to_edge(sensor_id, edge_id)
    
    def get_substitutes(self, sensor_id: str) :
        """获取可替代传感器列表"""
        return self.model.get_substitutes(sensor_id)
    
    def delete_sensor_and_relations(self, sensor_id: str) -> bool:
        """删除传感器"""
        return self.model.delete_sensor_and_relations(sensor_id)
    
    def get_all_nodes(self) -> List[Dict]:
        """获取所有节点"""
        return self.model.get_all_nodes()
    
    def auto_replace_sensor(self, failed_sensor_id: str) :
        """
        自动替换失效传感器：选择一个可用替代传感器并应用替换逻辑
        :return: (是否成功, 消息, 替代传感器ID)
        """
        substitutes = self.model.get_substitutes(failed_sensor_id)

        if not substitutes:
            return False, f"未找到可替代传感器：{failed_sensor_id}", None

        # 优先选择第一个状态为 active 的替代传感器
        for sub in substitutes:
            if sub['status'] == 'active':
                success, message = self.model.apply_replacement(
                    failed_sensor_id, sub['id']
                )
                event_id = time.time()
                return success, message, sub['id'] if success else None

        return False, f"找到的替代传感器均不可用（不处于 active 状态）", None
    
    def get_replace_graph_image(self, failed_id, replacement_id):
        return self.model.get_sub_graph_image(failed_id, replacement_id)