from py2neo import Graph, Node, Relationship, NodeMatcher
from .config import Config
class Neo4jDB:
    def __init__(self):
        self.driver = Graph('neo4j://localhost:7687', auth=("neo4j", "zouyi123456"), name='neo4j')

    def close(self):
        self.driver.close()

    def query(self, query, parameters={}):
        return self.driver.run(query, parameters)

