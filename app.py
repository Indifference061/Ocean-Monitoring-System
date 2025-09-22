from flask import Flask, request, jsonify, render_template, send_file
# from backend.models import OceanMonitoringModel
from backend.database import Neo4jDB
from backend.service import OceanMonitoringService
import io
import time

ocean_service = OceanMonitoringService()
app = Flask(__name__, template_folder='template')
@app.route('/')
def index():
    neo4j_url = "http://localhost:7474/browser/"
    return render_template("index.html", neo4j_url=neo4j_url)

@app.route('/add_sensor', methods=['POST'])
def add_sensor():
    start_time = time.time()
    data = request.json
    sensor_id = data["id"]
    sensor_type = data["type"]
    location = data["location"]
    measured_values = data.get("values", {})  # 这里保证 measured_values 是字典
    print(f"Received sensor data: {sensor_id}, {sensor_type}, {location}, {measured_values}")
    sensor = ocean_service.add_sensor(sensor_id, sensor_type, location, measured_values)
    end_time = time.time()
    print(f"添加传感器执行时间: {end_time - start_time:.4f} 秒")
    return jsonify({"message": "Sensor added", "id": sensor.identity})

@app.route('/get_nodes', methods=['GET'])
def get_nodes():
    """获取数据库中所有的节点"""
    nodes = ocean_service.get_all_nodes()
    return jsonify(nodes)

@app.route("/graph_image")
def graph_image():
    image_buf = ocean_service.get_graph_image()
    return send_file(image_buf, mimetype='image/png')

@app.route('/link_sensor_to_edge', methods=['POST'])
def link_sensor_to_edge():
    data = request.get_json()
    sensor_id = data.get('sensor_id')
    edge_id = data.get('edge_id')
    ocean_service.link_sensor_to_edge(sensor_id, edge_id)
    return jsonify({"message": "Sensor linked to EdgeNode successfully"})

@app.route('/link_edge_to_cloud', methods=['POST'])
def link_edge_to_cloud():
    data = request.get_json()
    edge_id = data.get('edge_id')
    cloud_id = data.get('cloud_id')
    ocean_service.link_edge_to_cloud(edge_id, cloud_id)
    return jsonify({"message": "EdgeNode linked to CloudResource successfully"})

@app.route("/get_substitutes/<sensor_id>")
def get_substitutes(sensor_id):
    substitutes = ocean_service.get_substitutes(sensor_id)
    return jsonify(substitutes)

@app.route("/auto_replace/<sensor_id>", methods=["POST"])
def auto_replace(sensor_id):
    start_time = time.time()
    success, message, replacement_id= ocean_service.auto_replace_sensor(sensor_id)
    end_time = time.time()
    print(f"传感器自动替换执行时间: {end_time - start_time:.4f} 秒")
    return jsonify({
            'success': success,
            'message': message,
            'replacement_id': replacement_id
        })

@app.route("/get_replace_graph", methods=["GET"])
def get_replace_graph():
    failed_id = request.args.get("failed_id")
    replacement_id = request.args.get("replacement_id")
    
    if not failed_id or not replacement_id:
        return "参数缺失", 400
    graph_image = ocean_service.get_replace_graph_image(failed_id, replacement_id)
    print(graph_image)
    return send_file(graph_image, mimetype='image/png')

@app.route("/send_replace_img")
def send_replace_img():
    return send_file("graph_sub.png", mimetype="image/png")

@app.route('/activate_sensor/<sensor_id>', methods=['POST'])
def activate_sensor(sensor_id):
    try:
        success = ocean_service.activate_sensor(sensor_id)
        if success:
            return jsonify({
                'success': success,
                'message': f"Sensor {sensor_id} 成功激活！"
            })
        else:
            return jsonify({"status": "error", "message": "Sensor not found"}), 404
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/delete_sensor/<sensor_id>", methods=['DELETE'])
def delete_sensor(sensor_id):
    try:
        success = ocean_service.delete_sensor_and_relations(sensor_id)
        if success:
            return jsonify({"status": "success"})
        else:
            return jsonify({"status": "error", "message": "Sensor not found"}), 404
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
    
if __name__ == '__main__':
    app.run(debug=True)
    
