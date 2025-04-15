import base64
import os
from py2neo import Graph, Node, Relationship
from concurrent.futures import ThreadPoolExecutor, as_completed
from .config import Config
from .llm_util import ask_spark
import re
from typing import Dict, List, Optional, Tuple
import matplotlib.pyplot as plt
from networkx.drawing.nx_agraph import graphviz_layout
import networkx as nx
import io
import time

class OceanMonitoringModel:
    def __init__(self):
        self.graph = Graph(uri=Config.NEO4J_URI, auth=(Config.NEO4J_USER, Config.NEO4J_PASSWORD))
        self.create_constraints()
        query = "MATCH (n) WHERE n:EdgeNode OR n:CloudResource SET n.status = 'active';"
        self.graph.run(query)

    def create_constraints(self):
        """确保唯一性约束，以防止重复数据"""
        self.graph.run("CREATE CONSTRAINT IF NOT EXISTS FOR (s:Sensor) REQUIRE s.id IS UNIQUE")
        self.graph.run("CREATE CONSTRAINT IF NOT EXISTS FOR (e:EdgeNode) REQUIRE e.id IS UNIQUE")
        self.graph.run("CREATE CONSTRAINT IF NOT EXISTS FOR (c:CloudResource) REQUIRE c.id IS UNIQUE")
    
    def create_sensor(self, sensor_id, sensor_type, location, measured_values):
        """创建传感器节点"""
        sensor = Node("Sensor", id=sensor_id, type=sensor_type, location=location, status="active", **measured_values)
        self.graph.merge(sensor, "Sensor", "id")
        return sensor
    
    def update_all_substitutable_relation(self, min_score: float = 8.0):
        """
        遍历所有已激活传感器的两两组合，使用大模型评估是否可替换。
        评估结果低于阈值将删除已有替换关系。
        """
        query = "MATCH (s:Sensor {status: 'active'}) RETURN s.id AS sensor_id"
        sensor_list = self.graph.run(query).data()
        sensor_ids = [s["sensor_id"] for s in sensor_list]

        for i in range(len(sensor_ids)):
            for j in range(i + 1, len(sensor_ids)):
                id1 = sensor_ids[i]
                id2 = sensor_ids[j]
                print(f"评估传感器 {id1} 和 {id2} 的替换关系")

                # 大模型评估
                evaluation = self.evaluate_replacement_with_llm(id1, id2)
                llm_response = evaluation.get("llm_evaluation", "")
                score_match = re.search(r'替换分数：(\d+\.?\d*)分', llm_response) or \
                            re.search(r'评分：(\d+\.?\d*)/10', llm_response) or \
                            re.search(r'得分：(\d+\.?\d*)', llm_response)

                if score_match:
                    try:
                        score = float(score_match.group(1))
                        print(f"评分为 {score}")

                        # 检查当前是否存在替换关系
                        existing_relation = self.graph.evaluate("""
                            MATCH (a:Sensor {id: $id1})-[r:SUBSTITUTABLE]->(b:Sensor {id: $id2})
                            RETURN r IS NOT NULL
                        """, id1=id1, id2=id2)

                        if score >= min_score:
                            # 创建关系（如尚未存在）
                            if not existing_relation:
                                self.create_substitutable_relation(id1, id2, "Sensor", "Sensor")
                                self.create_substitutable_relation(id2, id1, "Sensor", "Sensor")
                                print(f"创建替换关系: {id1} <-> {id2}")
                        else:
                            # 删除已有的低分替换关系
                            if existing_relation:
                                self.graph.run("""
                                    MATCH (a:Sensor {id: $id1})-[r:SUBSTITUTABLE]->(b:Sensor {id: $id2})
                                    DELETE r
                                """, id1=id1, id2=id2)
                                self.graph.run("""
                                    MATCH (b:Sensor {id: $id2})-[r:SUBSTITUTABLE]->(a:Sensor {id: $id1})
                                    DELETE r
                                """, id1=id1, id2=id2)
                                print(f"删除替换关系: {id1} <-> {id2} (评分: {score})")
                    except ValueError:
                        print(f"无法解析评分: {score_match.group(1)}")
                else:
                    print(f"未能在响应中找到有效评分: {llm_response[:50]}...")

        
    def create_sensor_with_llm_evaluation(self, sensor_id: str, sensor_type: str, 
                                        location: str, measured_values: Dict, 
                                        min_score: float = 8.0):
        """
        创建传感器并使用大模型评估自动建立替换关系
        """
        
        try:
            # 1. 创建传感器节点
            sensor = self.create_sensor(sensor_id, sensor_type, location, measured_values)
            
            # 2. 遍历查找传感器
            candidates_query = """
            MATCH (candidate:Sensor {status: 'active'})
            WHERE candidate.id <> $new_sensor_id
            AND candidate.location = $location
            RETURN candidate.id AS candidate_id
            """
            candidates = self.graph.run(candidates_query,
                                    sensor_type=sensor_type,
                                    new_sensor_id=sensor_id,
                                    location=location).data()
            
            if not candidates:
                print( "未找到可替换的候选传感器进行评估")
                return sensor
            
            def evaluate_and_create(candidate_id):
                try:
                    print(f"[线程] 评估 {sensor_id} <-> {candidate_id}")
                    evaluation = self.evaluate_replacement_with_llm(sensor_id, candidate_id)
                    llm_response = evaluation.get("llm_evaluation", "")
                    print(f"大模型评估结果: {llm_response}")
                    score_match = (
                        re.search(r'替换分数：(\d+\.?\d*)分', llm_response) or
                        re.search(r'评分：(\d+\.?\d*)/10', llm_response) or
                        re.search(r'得分：(\d+\.?\d*)', llm_response)
                    )
                    if score_match:
                        score = float(score_match.group(1))
                        if score >= min_score:
                            self.create_substitutable_relation(sensor_id, candidate_id, "Sensor", "Sensor")
                            self.create_substitutable_relation(candidate_id, sensor_id, "Sensor", "Sensor")
                            print(f"[替换成功] {sensor_id} <-> {candidate_id} (评分: {score})")
                    else:
                        print(f"[无评分] LLM响应: {llm_response[:50]}...")
                except Exception as e:
                    print(f"[错误] 评估 {candidate_id} 时出错: {str(e)}")

            # 使用线程池并发评估
            with ThreadPoolExecutor(max_workers=5) as executor:
                futures = [executor.submit(evaluate_and_create, c["candidate_id"]) for c in candidates]
                for future in as_completed(futures):
                    future.result()
            return sensor
        
        except Exception as e:
            print(f"创建过程中发生错误: {str(e)}")
            return sensor
    def create_edge_node(self, node_id, capacity, location):
        """创建边缘计算节点"""
        edge_node = Node("EdgeNode", id=node_id, capacity=capacity, location=location)
        self.graph.merge(edge_node, "EdgeNode", "id")
        return edge_node
    
    def create_cloud_resource(self, resource_id, provider, capacity):
        """创建云计算资源节点"""
        cloud = Node("CloudResource", id=resource_id, provider=provider, capacity=capacity)
        self.graph.merge(cloud, "CloudResource", "id")
        return cloud
    
    def get_substitutes(self, sensor_id):
        query = """
        MATCH (s:Sensor {id: $sensor_id})<-[:SUBSTITUTABLE_FOR]-(sub:Sensor)
        RETURN sub.id AS id, sub.type AS type, sub.location AS location, sub.status AS status
        """
        substitutes = self.graph.run(query, sensor_id=sensor_id).data()
        return substitutes

    def create_substitutable_relation(self, node1_id, node2_id, node1_type, node2_type):
        """创建可替代关系"""
        node1 = self.graph.nodes.match(node1_type, id=node1_id).first()
        node2 = self.graph.nodes.match(node2_type, id=node2_id).first()
        if node1 and node2:
            rel = Relationship(node1, "SUBSTITUTABLE_FOR", node2)
            self.graph.merge(rel)
    
    def link_sensor_to_edge(self, sensor_id, edge_id):
        """建立传感器和边缘计算节点的关系"""
        sensor = self.graph.nodes.match("Sensor", id=sensor_id).first()
        edge_node = self.graph.nodes.match("EdgeNode", id=edge_id).first()
        if sensor and edge_node:
            rel = Relationship(sensor, "SENDS_DATA_TO", edge_node)
            self.graph.merge(rel)
    
    def link_edge_to_cloud(self, edge_id, cloud_id):
        """建立边缘计算节点和云资源的关系"""
        edge_node = self.graph.nodes.match("EdgeNode", id=edge_id).first()
        cloud = self.graph.nodes.match("CloudResource", id=cloud_id).first()
        if edge_node and cloud:
            rel = Relationship(edge_node, "PROCESSES_DATA_WITH", cloud)
            self.graph.merge(rel)

    def get_all_nodes(self):
        """获取所有节点信息"""
        query = "MATCH (n) RETURN labels(n) AS labels, properties(n) AS properties"
        result = self.graph.run(query)
        nodes = [{"labels": record["labels"], "properties": record["properties"]} for record in result]
        return nodes
    
    def find_replacement_sensors(self, failed_sensor_id: str) -> List[Dict]:
        """
        查找可以替代失效传感器的候选传感器
        :param failed_sensor_id: 失效传感器的ID
        :return: 候选传感器列表及其相关信息
        """
        query = """
        MATCH (failed:Sensor {id: $failed_id})-[:SUBSTITUTABLE_FOR]->(candidate:Sensor)
        WHERE candidate.status = 'active'
        RETURN candidate.id AS id, candidate.type AS type, 
               candidate.location AS location, 
               properties(rel) AS relation_properties
        ORDER BY rel.similarity DESC
        """
        result = self.graph.run(query, failed_id=failed_sensor_id)
        return [dict(record) for record in result]
    
    def evaluate_replacement_with_llm(self, failed_sensor_id: str, 
                                     candidate_sensor_id: str) -> Dict:
        """
        使用大模型API评估传感器替换的合理性
        :return: 包含评估结果和建议的字典
        """
        # 获取两个传感器的详细信息
        query = """
        MATCH (failed:Sensor {id: $failed_id})
        MATCH (candidate:Sensor {id: $candidate_id})
        RETURN failed, candidate
        """
        result = self.graph.run(query, failed_id=failed_sensor_id, 
                               candidate_id=candidate_sensor_id).data()
        
        if not result:
            return {"error": "Sensors not found"}
        
        failed_sensor = result[0]['failed']
        candidate_sensor = result[0]['candidate']
        
        # 构建大模型提示
        prompt = f"""
        在海洋监控系统中，传感器{failed_sensor['id']}(类型:{failed_sensor['type']}, 
        位置:{failed_sensor['location']})已失效。考虑用传感器
        {candidate_sensor['id']}(类型:{candidate_sensor['type']}, 
        位置:{candidate_sensor['location']})作为替代。
        
        请评估此替换是否合适，考虑以下因素：
        1. 传感器类型的兼容性
        2. 位置差异的影响
        3. 测量范围和精度的差异
        4. 网络连接和边缘节点负载
        
        请给出总体评估结论(1-10分)（用“替换分数：x分”的形式）
        """
        
        # 调用大模型API
        llm_response = ask_spark(prompt)
        
        return {
            "failed_sensor": failed_sensor,
            "candidate_sensor": candidate_sensor,
            "llm_evaluation": llm_response
        }
    
    def apply_replacement(self, failed_sensor_id: str, 
                         replacement_sensor_id: str) -> Tuple[bool, str]:
        """
        应用传感器替换，转移所有关系
        :return: (是否成功, 消息)
        """
        try:
            # 获取失效传感器和替代传感器的边缘节点连接
            query = """
            MATCH (failed:Sensor {id: $failed_id})-[r:SENDS_DATA_TO]->(edge:EdgeNode)
            MATCH (replacement:Sensor {id: $replacement_id})
            WHERE replacement.status = 'active'
            MERGE (replacement)-[new_r:SENDS_DATA_TO]->(edge)
            SET failed.status = 'failed'
            RETURN edge.id AS edge_id
            """
            result = self.graph.run(query, failed_id=failed_sensor_id, 
                                  replacement_id=replacement_sensor_id).data()
            
            if not result:
                return False, "替换失败：可能替代传感器不存在或已失效"
            
            return True, f"成功替换！替代传感器已连接到边缘节点{result[0]['edge_id']}"
        except Exception as e:
            return False, f"替换过程中发生错误: {str(e)}"
    
    def delete_sensor_and_relations(self, sensor_id: str) -> bool:
        """
        删除指定ID的传感器节点及其所有关系
        """
        try:
            # 查询并删除该节点的所有关系
            delete_relations_query = """
            MATCH (s:Sensor {id: $sensor_id})-[r]-()
            DELETE r
            """
            self.graph.run(delete_relations_query, sensor_id=sensor_id)
            
            # 删除节点本身
            delete_node_query = """
            MATCH (s:Sensor {id: $sensor_id})
            DELETE s
            """
            self.graph.run(delete_node_query, sensor_id=sensor_id)
            
            return True
        except Exception as e:
            print(f"删除传感器{sensor_id}时出错: {str(e)}")
            return False
    
    def get_graph_image(self):
        nodes = self.graph.run("MATCH (n) RETURN n").data()
        rels = self.graph.run("MATCH (n)-[r]->(m) RETURN n, r, m").data()

        G = nx.DiGraph()
        node_labels = {}
        node_colors = []

        for record in nodes:
            n = record['n']
            node_id = n['id'] if 'id' in n else str(n.identity)
            node_type = list(n.labels)[0] if n.labels else "Node"
            G.add_node(n.identity, label=node_type)
            node_labels[n.identity] = f"{node_id}\n({node_type}"  
            # 上色
            if node_type == 'Sensor':
                node_colors.append('#b87fc9')
            elif node_type == 'EdgeNode':
                node_colors.append('#f78b38')
            elif node_type == 'CloudResource':
                node_colors.append('#56c0e0')
            else:
                node_colors.append('#cccccc')

        for record in rels:
            G.add_edge(record['n'].identity, record['m'].identity, label=record['r'].__class__.__name__)

        edge_labels = nx.get_edge_attributes(G, 'label')
        pos = nx.spring_layout(G, k=1, iterations=100, seed=42)

        plt.figure(figsize=(12, 10), facecolor='#f3f5f7')  # Neo4j 灰底
        nx.draw(G, pos, labels=node_labels, with_labels=True,
                node_color=node_colors, node_size=1800, font_size=10, font_color='black')

        nx.draw_networkx_edges(G, pos, arrows=True, edge_color='#999999', alpha=0.7,
                            connectionstyle='arc3,rad=0.15')
        nx.draw_networkx_edge_labels(G, pos, edge_labels=edge_labels, font_size=8)

        buf = io.BytesIO()
        plt.savefig(buf, format='png', bbox_inches='tight', facecolor='#f3f5f7')
        buf.seek(0)

        save_path = os.path.join(os.getcwd(), 'graph.png')
        plt.savefig(save_path, bbox_inches='tight', facecolor='#f3f5f7')
        print(f"[调试] 图像已保存到: {save_path}")
        plt.close()

        return buf
    
    def get_sub_graph_image(self, failed_id=None, replacement_id=None, event_id=None):
        # 获取所有节点和关系数据
        nodes = self.graph.run("MATCH (n) RETURN n").data()
        rels = self.graph.run("MATCH (n)-[r]->(m) RETURN n, r, m").data()

        # 创建有向图
        G = nx.DiGraph()
        node_labels = {}
        node_colors = []

        # 节点处理：根据失效传感器和替代传感器高亮
        for record in nodes:
            n = record['n']
            node_id = n['id'] if 'id' in n else str(n.identity)
            node_type = list(n.labels)[0] if n.labels else "Node"
            G.add_node(n.identity, label=node_type)
            
            label_str = f"{node_id}\n({node_type})"
            
            if node_type == 'Sensor':
                # 高亮失效传感器
                if failed_id and node_id == failed_id:
                    node_colors.append('#e74c3c')  # 失效 - 红色
                    label_str += "\n[Failed]"
                # 高亮替代传感器
                elif replacement_id and node_id == replacement_id:
                    node_colors.append('#27ae60')  # 替代 - 绿色
                    label_str += "\n[Substitute]"
                else:
                    node_colors.append('#b87fc9')
            elif node_type == 'EdgeNode':
                node_colors.append('#f78b38')
            elif node_type == 'CloudResource':
                node_colors.append('#56c0e0')
            else:
                node_colors.append('#cccccc')

            node_labels[n.identity] = label_str

        # 边处理：高亮替代传感器的连接
        highlight_edges = set()
        for record in rels:
            from_id = record['n'].identity
            to_id = record['m'].identity
            edge_label = record['r'].__class__.__name__
            G.add_edge(from_id, to_id, label=edge_label)

            # 高亮替代传感器连上的边缘节点连接
            if replacement_id and 'id' in record['n'] and record['n']['id'] == replacement_id and edge_label == 'SENDS_DATA_TO':
                highlight_edges.add((from_id, to_id))

        # 绘制图形
        pos = nx.spring_layout(G, k=1, iterations=100, seed=42)
        plt.figure(figsize=(12, 10), facecolor='#f3f5f7')  # Neo4j 灰底
        nx.draw(G, pos, labels=node_labels, with_labels=True, node_color=node_colors, node_size=1800, font_size=10, font_color='black')
        
        # 绘制边：分为普通边和高亮边
        normal_edges = [(u, v) for u, v in G.edges() if (u, v) not in highlight_edges]
        highlighted_edges = list(highlight_edges)

        nx.draw_networkx_edges(G, pos, edgelist=normal_edges, arrows=True, edge_color='#999999', alpha=0.5, connectionstyle='arc3,rad=0.1')
        nx.draw_networkx_edges(G, pos, edgelist=highlighted_edges, arrows=True, edge_color='#27ae60', width=2.5, connectionstyle='arc3,rad=0.15')
        nx.draw_networkx_edge_labels(G, pos, font_size=8)

        buf = io.BytesIO()
        plt.savefig(buf, format='png', bbox_inches='tight', facecolor='#f3f5f7')
        buf.seek(0)
        
        save_path = os.path.join(os.getcwd(), 'graph_sub.png')
        plt.savefig(save_path, bbox_inches='tight', facecolor='#f3f5f7')
        print(f"[调试] 图像已保存到: {save_path}")
        plt.close()

        return buf