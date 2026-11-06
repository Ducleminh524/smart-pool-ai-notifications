# Smart Pool - Roboflow & Kaggle Slack Monitor (2 channels)

## Kênh thông báo
- Roboflow -> `#roboflow-report` (`ROBOFLOW_SLACK_WEBHOOK_URL`)
- Kaggle -> `#kaggle-report` (`KAGGLE_SLACK_WEBHOOK_URL`)

Hai webhook phải được tạo cho đúng channel. **Không** dùng `SLACK_WEBHOOK_URL` chung nữa.

## 1. Cấu hình trên GitHub
Vào repo -> Settings -> Secrets and variables -> Actions:

| Type | Tên | Nội dung |
|---|---|---|
| Secret | `ROBOFLOW_API_KEY` | Private API key Roboflow |
| Secret | `ROBOFLOW_SLACK_WEBHOOK_URL` | Incoming Webhook chọn `#roboflow-report` |
| Secret | `KAGGLE_SLACK_WEBHOOK_URL` | Incoming Webhook chọn `#kaggle-report` |
| Secret | `KAGGLE_API_TOKEN` | Kaggle API token, hoặc dùng username/key cũ |
| Variable | `ROBOFLOW_WORKSPACE` | Workspace slug (trong URL project) |
| Variable | `ROBOFLOW_PROJECT` | Project slug (trong URL project) |
| Variable | `KAGGLE_ACCOUNT_USERNAME` | Username tài khoản Kaggle cá nhân (KHÔNG phải secret) |
| Variable | `KAGGLE_NOTEBOOKS` | Không bắt buộc; thêm notebook muốn theo dõi, cách nhau bởi dấu phẩy |

**Lưu ý phân biệt:** `KAGGLE_ACCOUNT_USERNAME` (GitHub Variable) là tên người dùng cần *giám sát*. `KAGGLE_USERNAME` (GitHub Secret) và `KAGGLE_KEY` (GitHub Secret) chỉ dùng cho cách xác thực Kaggle API cũ. Nếu bạn dùng `KAGGLE_API_TOKEN` thì không cần khai báo `KAGGLE_USERNAME`/`KAGGLE_KEY`.

Kaggle CLI liệt kê notebook với `kaggle kernels list --user username --csv`; chương trình chỉ kiểm tra trạng thái của tối đa 1000 notebook (10 trang x 100) trong tài khoản. Để tránh bỏ sót trạng thái khi một run xảy ra giữa 2 lần quét, nên thêm notifier trực tiếp vào notebook.

## 2. Cập nhật GitHub repository
Giải nén ZIP, **chép nội dung bên trong thư mục `slack_ai_monitor_2channels`** vào root repo, giữ nguyên đường dẫn `.github/workflows/monitor.yml`. Thay thế các file `scripts/monitor.py`, `scripts/kaggle_notify.py`, `requirements.txt` cũ. Nên xóa workflow cũ nếu tên file khác `monitor.yml`, tránh chạy trùng.

Settings -> Actions -> General -> Workflow permissions -> **Read and write permissions**. Nếu branch protection chặn GitHub bot push thì cần chỉnh phù hợp.

## 3. Chạy thử
Actions -> **Roboflow and Kaggle - Separate Slack Channels** -> Run workflow.

Lần đầu lấy baseline của mỗi nguồn sẽ gửi một tin nhắn khởi tạo vào đúng channel. Lần sau báo khi project Roboflow thay đổi phiên bản/số ảnh, hoặc notebook Kaggle mới xuất hiện/trạng thái lần chạy gần nhất đổi. Thời gian quét mặc định 15 phút, lịch chạy GitHub Actions có thể trễ. Trạng thái lưu tại `state/monitor.json` và được commit tự động, không chứa API keys.

## 4. Training trực tiếp trên Kaggle
Trong Kaggle Notebook -> Add-ons -> Secrets, lưu secret **`KAGGLE_SLACK_WEBHOOK_URL`**, cho notebook quyền đọc secret và (nếu được phép) bật Internet. Dán nội dung `scripts/kaggle_notify.py` vào cell đầu, đặt `RUN_BY` thành tên của bạn, rồi gọi `notify()` trước và sau `model.train()` theo ví dụ trong file.

## 5. Giới hạn cần biết
- Roboflow metadata không bảo đảm có danh tính người upload / gán nhãn, thay đổi annotation từng ảnh, hoặc job status.
- Kaggle status là trạng thái **lần chạy notebook được lưu/versioned**, không phải trạng thái tức thời của mọi interactive session. Một lần chạy nhanh có thể không hiện đủ các trạng thái khi kiểm tra theo lịch.
- Tên tài khoản sở hữu notebook không chứng minh người trực tiếp bấm Run; `RUN_BY` trong notebook là thông tin tự khai báo.
- Nếu notification gửi thành công rồi chương trình bị lỗi trước khi cập nhật state, lần chạy sau có thể gửi lại. Nếu có nhiều sự kiện và gửi thất bại giữa chừng, có thể gửi lặp một vài sự kiện khi retry.
- Nếu tài khoản có nhiều hơn 1000 notebook, nên dùng `KAGGLE_NOTEBOOKS` hoặc tùy biến phân trang.
- Mỗi source xử lý độc lập; nếu 1 nguồn lỗi, nguồn còn lại vẫn có thể gửi thông báo, nhưng workflow được đánh dấu thất bại để bạn kiểm tra.
- Cấu hình mẫu được kiểm thử cú pháp/logic nội bộ, **chưa kiểm tra bằng API key thực tế**.
