import json
import os
import socket
import threading

HOST = '0.0.0.0'
PORT = 8080
# Caminho apontando para a pasta 'data'
FILE_DB = os.path.join('data', 'agendamentos.json')

file_lock = threading.Lock()

def load_agendamentos():
    if not os.path.exists(FILE_DB):
        return []
    with open(FILE_DB, 'r', encoding='utf-8') as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return []

def save_agendamentos(data):
    os.makedirs('data', exist_ok=True)
    with open(FILE_DB, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def handle_client(conn, addr):
    try:
        raw_data = conn.recv(4096).decode('utf-8')
        if not raw_data:
            return

        lines = raw_data.split('\r\n')
        request_line = lines[0]
        parts = request_line.split(' ')
        if len(parts) < 2:
            return

        method, path = parts[0], parts[1]

        # Roteamento considerando a estrutura de pastas
        if method == 'GET':
            if path in ['/', '/index.html']:
                serve_file(conn, os.path.join('pages', 'index.html'), 'text/html')
            elif path in ['/style.css', '/css/style.css']:
                serve_file(conn, os.path.join('css', 'style.css'), 'text/css')
            elif path in ['/agendamentos.json', '/api/agendamentos']:
                with file_lock:
                    dados = load_agendamentos()
                send_json_response(conn, 200, dados)
            else:
                send_response(conn, 404, 'text/plain', '404 Not Found')

        elif method == 'POST' and path == '/api/agendamentos':
            body_index = raw_data.find('\r\n\r\n')
            body = raw_data[body_index + 4:] if body_index != -1 else ""

            try:
                payload = json.loads(body)
                paciente = payload.get('paciente')
                medico = payload.get('medico')
                data_hora = payload.get('data_hora')

                if not paciente or not medico or not data_hora:
                    send_json_response(conn, 400, {"status": "error", "message": "Dados incompletos."})
                    return

                with file_lock:
                    agendamentos = load_agendamentos()
                    conflito = any(
                        a['medico'] == medico and a['data_hora'] == data_hora 
                        for a in agendamentos
                    )

                    if conflito:
                        send_json_response(conn, 409, {
                            "status": "error", 
                            "message": "Horário já reservado para este médico!"
                        })
                        return

                    novo_id = max([a.get('id', 0) for a in agendamentos], default=0) + 1
                    novo_agendamento = {
                        "id": novo_id,
                        "paciente": paciente,
                        "medico": medico,
                        "data_hora": data_hora,
                        "status": "Confirmado"
                    }
                    agendamentos.append(novo_agendamento)
                    save_agendamentos(agendamentos)

                send_json_response(conn, 201, {"status": "success", "agendamento": novo_agendamento})

            except json.JSONDecodeError:
                send_json_response(conn, 400, {"status": "error", "message": "JSON inválido."})

        elif method == 'PUT' and path == '/api/agendamentos':
            body_index = raw_data.find('\r\n\r\n')
            body = raw_data[body_index + 4:] if body_index != -1 else ""

            try:
                payload = json.loads(body)
                agendamento_id = payload.get('id')
                novo_status = payload.get('status')

                with file_lock:
                    agendamentos = load_agendamentos()
                    for item in agendamentos:
                        if item['id'] == agendamento_id:
                            item['status'] = novo_status
                            save_agendamentos(agendamentos)
                            send_json_response(conn, 200, {"status": "success", "message": "Status atualizado!"})
                            return

                send_json_response(conn, 404, {"status": "error", "message": "Agendamento não encontrado."})

            except json.JSONDecodeError:
                send_json_response(conn, 400, {"status": "error", "message": "JSON inválido."})

        elif method == 'DELETE' and path == '/api/agendamentos':
            body_index = raw_data.find('\r\n\r\n')
            body = raw_data[body_index + 4:] if body_index != -1 else ""

            try:
                payload = json.loads(body)
                agendamento_id = payload.get('id')

                with file_lock:
                    agendamentos = load_agendamentos()
                    agendamentos_filtrados = [a for a in agendamentos if a['id'] != agendamento_id]

                    if len(agendamentos_filtrados) == len(agendamentos):
                        send_json_response(conn, 404, {"status": "error", "message": "ID não encontrado."})
                        return

                    save_agendamentos(agendamentos_filtrados)
                    send_json_response(conn, 200, {"status": "success", "message": "Agendamento removido!"})

            except json.JSONDecodeError:
                send_json_response(conn, 400, {"status": "error", "message": "JSON inválido."})
    
    except Exception as e:
        print(f"Erro na conexão com {addr}: {e}")
    finally:
        conn.close()

def serve_file(conn, filepath, content_type):
    if os.path.exists(filepath):
        with open(filepath, 'rb') as f:
            content = f.read()
        header = (
            f"HTTP/1.1 200 OK\r\n"
            f"Content-Type: {content_type}; charset=utf-8\r\n"
            f"Content-Length: {len(content)}\r\n"
            f"Connection: close\r\n\r\n"
        )
        conn.sendall(header.encode('utf-8') + content)
    else:
        send_response(conn, 404, 'text/plain', f'404 File Not Found: {filepath}')

def send_response(conn, status_code, content_type, text):
    content = text.encode('utf-8')
    header = (
        f"HTTP/1.1 {status_code} OK\r\n"
        f"Content-Type: {content_type}\r\n"
        f"Content-Length: {len(content)}\r\n"
        f"Connection: close\r\n\r\n"
    )
    conn.sendall(header.encode('utf-8') + content)

def send_json_response(conn, status_code, data):
    body = json.dumps(data, ensure_ascii=False).encode('utf-8')
    status_text = "OK" if status_code < 400 else ("Conflict" if status_code == 409 else "Bad Request")
    header = (
        f"HTTP/1.1 {status_code} {status_text}\r\n"
        f"Content-Type: application/json; charset=utf-8\r\n"
        f"Content-Length: {len(body)}\r\n"
        f"Connection: close\r\n\r\n"
    )
    conn.sendall(header.encode('utf-8') + body)

def start_server():
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    
    server_socket.bind((HOST, PORT))
    server_socket.listen(10)
    print(f"[*] Servidor TCP Clínico rodando em http://{HOST}:{PORT}")

    while True:
        conn, addr = server_socket.accept()
        client_thread = threading.Thread(target=handle_client, args=(conn, addr))
        client_thread.daemon = True
        client_thread.start()

if __name__ == '__main__':
    start_server()