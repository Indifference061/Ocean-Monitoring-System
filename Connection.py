from py2neo import Graph, Node, Relationship, NodeMatcher
 
graph = Graph('bolt://localhost:7687', auth=("neo4j", "zouyi123456"), name='neo4j')
a = Node('Person', name='Alice')
b = Node('Person', name='Bob')
graph.create(a)
graph.create(b)
r = Relationship(a, 'KNOWS', b)
graph.create(r)
print(a, b, r)
a['age'] = 20
b['age'] = 21
r['time'] = '2017/08/31'
print(a, b, r)