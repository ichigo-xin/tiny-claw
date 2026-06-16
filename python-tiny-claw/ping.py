from flask import Flask, jsonify, request
import time

app = Flask(__name__)

@app.route('/ping', methods=['GET'])
def ping():
    """
    简单的 ping 接口，返回服务器状态和当前时间戳
    """
    try:
        response = {
            'code': 200,
            'message': 'pong',
            'timestamp': int(time.time()),
            'ip': request.remote_addr
        }
        return jsonify(response)
    except Exception as e:
        return jsonify({
            'code': 500,
            'message': f'服务器错误: {str(e)}'
        }), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)