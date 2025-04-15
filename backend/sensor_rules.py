from . import database as db  # 适用于 Flask 蓝图或 Python package

def check_replacement(db, sensor_type):
    query = """
    MATCH (s1:Sensor)-[:Replacement]->(s2:Sensor)
    WHERE s1.type = $sensor_type
    RETURN s2
    """
    return db.run_query(query, {"sensor_type": sensor_type})