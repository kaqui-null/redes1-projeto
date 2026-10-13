import socket
from pathlib import Path
import json
from urllib.parse import parse_qs

HOST = "127.0.0.1"
PORT = 8000

BASE_DIR = Path(__file__).resolve().parent
DATA_FILE = BASE_DIR / "data/appointments.json"

PAGES = {
    "/": "index.html",
    "/appointments": "appointments.html",
    "/create": "create.html",
    "/edit": "edit.html",
}

# inicial vazio se nao existir json
def load_appointments():
    if not DATA_FILE.exists():
        return []
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError:
        return []

def save_appointments(appointments):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(appointments, f, indent=4)

def check_time_conflict(date, start_time, end_time, exclude_id=None):
    # formato de tempo esperado "HH:MM"
    appointments = load_appointments()
    for appt in appointments:
        if exclude_id and str(appt.get("id")) == str(exclude_id):
            continue
        if appt.get("date") == date:
            existing_start = appt.get("startTime")
            existing_end = appt.get("endTime")

            if start_time < existing_end and existing_start < end_time:
                return True

    return False

def create_response(status, content_type, body):

    if isinstance(body, dict) or isinstance(body, list):
        body = json.dumps(body)
        content_type = "application/json; charset=utf-8"

    body = body.encode("utf-8")

    headers = (
        f"HTTP/1.1 {status}\r\n"
        f"Content-Type: {content_type}\r\n"
        f"Content-Length: {len(body)}\r\n"
        "Connection: close\r\n"
        "\r\n"
    )

    return headers.encode("ascii") + body

def handle_request(request):
    # Separate headers/request line from body
    parts = request.split(b"\r\n\r\n", 1)
    header_part = parts[0].decode("ascii", errors="replace")
    body_bytes = parts[1] if len(parts) > 1 else b""

    if not header_part:
        return create_response("400 Bad Request", "text/plain; charset=utf-8", "Invalid request")

    # Get the request line (the first line of the headers)
    lines = header_part.split("\r\n")
    request_line = lines[0] if lines else ""

    req_parts = request_line.split()
    if len(req_parts) != 3:
        return create_response("400 Bad Request", "text/plain; charset=utf-8", "Invalid HTTP request")

    method, path, version = req_parts

    # Paginas HTML
    if method == "GET" and path in PAGES:
        file_path = BASE_DIR / "pages" / PAGES[path]
        try:
            content = file_path.read_text(encoding="utf-8")
            return create_response("200 OK", "text/html; charset=utf-8", content)
        except FileNotFoundError:
            return create_response("404 Not Found", "text/plain; charset=utf-8", "HTML page not found")

    # Estilo
    if method == "GET" and path == "/css/style.css":
        file_path = BASE_DIR / "css" / "style.css"
        try:
            content = file_path.read_text(encoding="utf-8")
            return create_response("200 OK", "text/css; charset=utf-8", content)
        except FileNotFoundError:
            return create_response("404 Not Found", "text/plain; charset=utf-8", "CSS file not found")

    # --- API Endpoints ---

    # LIST: GET /api/appointments
    if method == "GET" and path == "/api/appointments":
        appointments = load_appointments()
        return create_response("200 OK", "application/json; charset=utf-8", appointments)

    # CREATE: POST /api/appointments
    if method == "POST" and path == "/api/appointments":
        try:
            data = json.loads(body_bytes.decode("utf-8"))
        except json.JSONDecodeError:
            return create_response("400 Bad Request", "text/plain; charset=utf-8", "Invalid JSON payload")

        # Validacao
        required_fields = ["name", "description", "date", "startTime", "endTime", "status"]
        if not all(field in data for field in required_fields):
            return create_response("400 Bad Request", "text/plain; charset=utf-8", "Missing required fields")

        date = data["date"]
        start_time = data["startTime"]
        end_time = data["endTime"]

        if check_time_conflict(date, start_time, end_time):
            return create_response("409 Conflict", "text/plain; charset=utf-8", "Time slot conflicts with an existing appointment.")

        appointments = load_appointments()

        # novo ID
        new_id = max([appt.get("id", 0) for appt in appointments], default=0) + 1

        # novo appointment no JSON
        new_appointment = {
            "id": new_id,
            "name": data["name"],
            "description": data["description"],
            "date": date,
            "startTime": start_time,
            "endTime": end_time,
            "status": data["status"]
        }

        appointments.append(new_appointment)
        save_appointments(appointments)
        return create_response("201 Created", "application/json; charset=utf-8", new_appointment)

    # EDIT/UPDATE: PUT /api/appointments/<id>
    if method == "PUT" and path.startswith("/api/appointments/"):
        try:
            appt_id = int(path.split("/")[-1])
        except ValueError:
            return create_response("400 Bad Request", "text/plain; charset=utf-8", "Invalid appointment ID")

        try:
            data = json.loads(body_bytes.decode("utf-8"))
        except json.JSONDecodeError:
            return create_response("400 Bad Request", "text/plain; charset=utf-8", "Invalid JSON payload")

        date = data.get("date")
        start_time = data.get("startTime")
        end_time = data.get("endTime")

        # Check time conflicts excluding current appointment ID
        if check_time_conflict(date, start_time, end_time, exclude_id=appt_id):
            return create_response("409 Conflict", "text/plain; charset=utf-8", "Time slot conflicts with another appointment.")

        appointments = load_appointments()
        updated = False

        for appt in appointments:
            if appt.get("id") == appt_id:
                appt["name"] = data.get("name", appt["name"])
                appt["description"] = data.get("description", appt["description"])
                appt["date"] = date
                appt["startTime"] = start_time
                appt["endTime"] = end_time
                appt["status"] = data.get("status", appt["status"])
                updated = True
                break

        if not updated:
            return create_response("404 Not Found", "text/plain; charset=utf-8", "Appointment not found")

        save_appointments(appointments)
        return create_response("200 OK", "application/json; charset=utf-8", {"message": "Updated successfully"})

    # DELETE: DELETE /api/appointments/<id>
    if method == "DELETE" and path.startswith("/api/appointments/"):
        try:
            appt_id = int(path.split("/")[-1])
        except ValueError:
            return create_response("400 Bad Request", "text/plain; charset=utf-8", "Invalid appointment ID")

        appointments = load_appointments()
        filtered_appointments = [appt for appt in appointments if appt.get("id") != appt_id]

        if len(filtered_appointments) == len(appointments):
            return create_response("404 Not Found", "text/plain; charset=utf-8", "Appointment not found")

        save_appointments(filtered_appointments)
        return create_response("200 OK", "application/json; charset=utf-8", {"message": "Deleted successfully"})

    return create_response("404 Not Found", "text/plain; charset=utf-8", "Route not found")


def main():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind((HOST, PORT))
        server.listen()

        print(f"Server running at http://{HOST}:{PORT}")

        while True:
            connection, address = server.accept()
            with connection:
                request = connection.recv(8192)
                response = handle_request(request)
                connection.sendall(response)


if __name__ == "__main__":
    main()
