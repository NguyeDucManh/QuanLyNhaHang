# Đăng ký, xếp và duyệt ca

Phụ thuộc gói P0 Issue10/PR11; không merge lại PR9 nếu shortcut đã có. Không thay
thực đơn, recipes, giá hoặc ảnh. Không tự tạo tài khoản hoặc Attendance.

## Tuần sau

1. ADMIN/MANAGER vào Nhân sự → Lịch làm việc → Đăng ký và xếp ca tuần sau
   (`/management/roster/`). Chọn chuyên môn/chức vụ phù hợp từng ca, giới hạn nghỉ
   ít nhất 11 giờ, tối đa 48 giờ và 6 ca/tuần, một ngày nghỉ; xác nhận hạn đăng ký.
2. Nhân viên vào Lịch làm → Đăng ký ca tuần sau (`/work/shift-registration/`).
   Chọn ca có thể làm từng ngày, mức ưu tiên, hoặc đánh dấu không thể làm. Không
   chọn ca không được coi là đồng ý làm ca đó. Sửa/xóa trước hạn, không chỉnh hộ
   người khác. Bản ghi duy nhất theo nhân viên/tuần, cập nhật khóa tuần tuần tự.
3. Quản lý xem đăng ký, xem đề xuất GA, số ca/người và suất còn thiếu. Thiếu người
   được báo rõ, không tự phân ngược nguyện vọng, sai chuyên môn hoặc vượt giờ.
4. Duyệt đúng preview sẽ lưu WorkSchedule APPROVED và người/thời điểm duyệt thật.
   Sau công bố nhân viên xem lịch chính thức trong `/work/?tab=schedule`.
   Camera/FaceID vẫn cần hồ sơ thật, model/enrollment và ca trong cửa sổ cho phép.

Không lấy thời điểm đăng ký hay lịch APPROVED làm bằng chứng nhân viên đã đi làm.
Quản lý có thể preview trước hạn; publish khóa sửa đăng ký nên phải review trước
khi bấm duyệt. Preview có chữ ký, hạn 24h, recheck fingerprint sau khóa Employee/
Shift/tuần. Dữ liệu đổi phải preview lại; không bỏ qua xung đột hoặc overwrite.

## Bổ sung 5 tuần lịch từ dữ liệu đang có

```sh
python manage.py preview_staff_roster --reference-date 2026-11-18 --policy approved-roster-rules.json --output private-roster-preview.json
python manage.py apply_staff_roster --plan private-roster-preview.json --actor ADMIN_USERNAME
```

Hai lệnh trên không ghi. Preview chứa 19/10–22/11; ngày tham chiếu mặc định là
ngày Asia/Ho_Chi_Minh. JSON policy phải có allowed_positions theo ID ca/ID chức vụ,
min_rest_hours, max_weekly_hours, max_weekly_shifts và được quản lý đối chiếu thực tế.
Không coi ví dụ kỹ thuật là chính sách vận hành đã được duyệt.

Chỉ sau backup và phê duyệt dữ liệu đúng hash, thêm `--apply --approved-digest HASH`.
`--approve-current` chỉ duyệt ca chưa kết thúc với approved_at hiện tại. Ca quá khứ
luôn DRAFT, ghi note nhập bổ sung hồi tố/thời điểm tạo/nguồn, không backdate approval
hoặc tạo Attendance. Không ghi đè lịch cũ, không sửa bảng lương khóa. Một transaction
ghi cả lịch và audit; lỗi rollback toàn bộ, áp dụng lặp cùng plan không tạo trùng.

## Schema và rollout

Migration **0025_staff_roster_registration** thêm RosterWeek, ShiftRegistration,
FK PROTECT, unique tuần và unique nhân viên/tuần. Phụ thuộc 0024; không tự chạy
0022–0025 trên local gốc hoặc Render. Chỉ apply trên DB test trong kiểm thử.
Nếu schema chưa có, trang chức năng trả 503 có thông báo rõ; lịch/chấm công hiện
có không bị tự migrate hoặc thay đổi. Không bật ba feature flag nghiệp vụ.

Rollback code không reverse/drop bảng chứa đăng ký. Giữ schema và dữ liệu đã có;
nếu cần hủy lịch, quản trị duyệt qua nghiệp vụ hủy riêng, không DELETE/restore đè.
Các lịch/đăng ký thử chỉ được lưu ở DB test được định danh rõ.
