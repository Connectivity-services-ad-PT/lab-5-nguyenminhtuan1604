# Phiếu hẹn tích hợp — Buổi 6

Nhóm gọi (consumer): Access Gate Service
Nhóm được gọi (provider): Core Business (team-core)

Kiểu giao tiếp: [x] REST sync

URL provider (ở nhà): http://localhost:8000
URL provider (Buổi 6): http://172.20.10.__:8000

Method: POST
Path: /policy/access-check

Request mẫu:
{
  "cardId": "RFID-2026-001",
  "gateId": "GATE-01",
  "direction": "ENTER",
  "timestamp": "2026-06-15T07:00:00Z"
}

Response mong đợi:
{
  "cardId": "RFID-2026-001",
  "gateId": "GATE-01",
  "decision": "ALLOW",
  "reason": null,
  "policyId": "POL-2026-001",
  "checkedAt": "..."
}

Xử lý lỗi: Timeout 5 giây, trả 503 nếu Core Business không phản hồi

Đã test ở nhà: [x] Rồi
Đã test qua hotspot iPhone: [ ] Chưa
