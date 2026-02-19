"""Web dashboard for monitoring download and upload progress."""

import json
import sqlite3
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from eroasmr_scraper.config import settings

app = FastAPI(
    title="EroASMR Scraper Dashboard",
    description="Monitor download and upload progress",
    version="1.0.0",
)


class DashboardStats(BaseModel):
    """Dashboard statistics."""

    # Video counts
    total_videos: int
    completed: int
    failed: int
    pending: int
    downloading: int
    not_started: int

    # Upload counts
    telegram_uploads: int
    mock_uploads: int

    # Disk info
    disk_total_gb: float
    disk_used_gb: float
    disk_free_gb: float
    disk_free_percent: float

    # Recent activity
    recent_downloads: list[dict]
    recent_uploads: list[dict]
    recent_failures: list[dict]

    # Timestamp
    last_updated: str


def get_db_connection():
    """Get database connection."""
    db_path = Path(settings.db.path)
    if not db_path.exists():
        return None
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


def get_disk_info() -> dict:
    """Get disk space information."""
    import shutil
    total, used, free = shutil.disk_usage("/")
    return {
        "disk_total_gb": round(total / (1024**3), 1),
        "disk_used_gb": round(used / (1024**3), 1),
        "disk_free_gb": round(free / (1024**3), 1),
        "disk_free_percent": round(free / total * 100, 1),
    }


@app.get("/api/stats", response_model=DashboardStats)
async def get_stats():
    """Get dashboard statistics."""
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500, detail="Database not found")

    try:
        cursor = conn.cursor()

        # Video counts
        cursor.execute("SELECT COUNT(*) FROM videos")
        total_videos = cursor.fetchone()[0]

        # Download stats
        cursor.execute("SELECT status, COUNT(*) FROM downloads GROUP BY status")
        download_counts = {row[0]: row[1] for row in cursor.fetchall()}

        completed = download_counts.get("completed", 0)
        failed = download_counts.get("failed", 0)
        pending = download_counts.get("pending", 0)
        downloading = download_counts.get("downloading", 0)

        # Not started = total videos - all download records
        cursor.execute("SELECT COUNT(*) FROM downloads")
        total_downloads = cursor.fetchone()[0]
        not_started = total_videos - total_downloads

        # Upload stats
        cursor.execute(
            "SELECT storage_type, COUNT(*) FROM storage_locations GROUP BY storage_type"
        )
        upload_counts = {row[0]: row[1] for row in cursor.fetchall()}
        telegram_uploads = upload_counts.get("telegram", 0)
        mock_uploads = upload_counts.get("mock", 0)

        # Recent downloads (last 10)
        cursor.execute("""
            SELECT d.slug, d.status, d.local_path, d.file_size, d.downloaded_at,
                   v.title
            FROM downloads d
            LEFT JOIN videos v ON d.slug = v.slug
            WHERE d.status = 'completed'
            ORDER BY d.downloaded_at DESC
            LIMIT 10
        """)
        recent_downloads = [
            {
                "slug": row[0],
                "status": row[1],
                "local_path": row[2],
                "file_size": row[3],
                "file_size_mb": round(row[3] / (1024**2), 1) if row[3] else 0,
                "downloaded_at": row[4],
                "title": row[5] or row[0],
            }
            for row in cursor.fetchall()
        ]

        # Recent uploads (last 10)
        cursor.execute("""
            SELECT s.slug, s.storage_type, s.location_id, s.location_url, s.uploaded_at,
                   v.title
            FROM storage_locations s
            LEFT JOIN videos v ON s.slug = v.slug
            ORDER BY s.uploaded_at DESC
            LIMIT 10
        """)
        recent_uploads = [
            {
                "slug": row[0],
                "storage_type": row[1],
                "location_id": row[2],
                "location_url": row[3],
                "uploaded_at": row[4],
                "title": row[5] or row[0],
            }
            for row in cursor.fetchall()
        ]

        # Recent failures (last 10)
        cursor.execute("""
            SELECT d.slug, d.error_message, v.title
            FROM downloads d
            LEFT JOIN videos v ON d.slug = v.slug
            WHERE d.status = 'failed'
            ORDER BY d.downloaded_at DESC
            LIMIT 10
        """)
        recent_failures = [
            {
                "slug": row[0],
                "error": row[1],
                "title": row[2] or row[0],
            }
            for row in cursor.fetchall()
        ]

        disk_info = get_disk_info()

        return DashboardStats(
            total_videos=total_videos,
            completed=completed,
            failed=failed,
            pending=pending,
            downloading=downloading,
            not_started=not_started,
            telegram_uploads=telegram_uploads,
            mock_uploads=mock_uploads,
            last_updated=datetime.now().isoformat(),
            recent_downloads=recent_downloads,
            recent_uploads=recent_uploads,
            recent_failures=recent_failures,
            **disk_info,
        )
    finally:
        conn.close()


@app.get("/api/activity")
async def get_activity(limit: int = 50):
    """Get recent activity log."""
    log_dir = Path("logs")
    if not log_dir.exists():
        return {"activity": []}

    # Find the most recent log file
    log_files = sorted(log_dir.glob("pipeline_*.log"), reverse=True)
    if not log_files:
        return {"activity": []}

    activity = []
    try:
        with open(log_files[0], "r") as f:
            lines = f.readlines()[-limit:]
            for line in lines:
                line = line.strip()
                if line:
                    activity.append(line)
    except Exception:
        pass

    return {"activity": activity, "log_file": str(log_files[0])}


@app.get("/", response_class=HTMLResponse)
async def dashboard():
    """Serve the dashboard HTML."""
    html_content = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>EroASMR Scraper Dashboard</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, sans-serif;
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
            color: #eee;
            min-height: 100vh;
            padding: 20px;
        }
        .container {
            max-width: 1400px;
            margin: 0 auto;
        }
        header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 30px;
            padding-bottom: 20px;
            border-bottom: 1px solid #333;
        }
        header h1 {
            font-size: 24px;
            color: #00d4ff;
        }
        .last-updated {
            font-size: 12px;
            color: #888;
        }
        .grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }
        .card {
            background: rgba(255, 255, 255, 0.05);
            border-radius: 12px;
            padding: 20px;
            border: 1px solid rgba(255, 255, 255, 0.1);
        }
        .card h2 {
            font-size: 14px;
            color: #888;
            text-transform: uppercase;
            letter-spacing: 1px;
            margin-bottom: 15px;
        }
        .stat-value {
            font-size: 48px;
            font-weight: bold;
            color: #00d4ff;
        }
        .stat-label {
            font-size: 14px;
            color: #aaa;
            margin-top: 5px;
        }
        .progress-bar {
            background: #333;
            border-radius: 10px;
            height: 20px;
            overflow: hidden;
            margin: 10px 0;
        }
        .progress-fill {
            height: 100%;
            background: linear-gradient(90deg, #00d4ff, #00ff88);
            transition: width 0.5s ease;
        }
        .progress-text {
            text-align: center;
            font-size: 12px;
            color: #aaa;
        }
        .stats-grid {
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 15px;
            margin-top: 15px;
        }
        .mini-stat {
            text-align: center;
            padding: 10px;
            background: rgba(0, 0, 0, 0.2);
            border-radius: 8px;
        }
        .mini-stat-value {
            font-size: 24px;
            font-weight: bold;
        }
        .mini-stat-label {
            font-size: 11px;
            color: #888;
        }
        .status-completed { color: #00ff88; }
        .status-failed { color: #ff4757; }
        .status-pending { color: #ffa502; }
        .status-downloading { color: #00d4ff; }
        .status-not-started { color: #888; }

        .activity-list {
            max-height: 300px;
            overflow-y: auto;
        }
        .activity-item {
            padding: 10px;
            border-bottom: 1px solid #333;
            font-size: 13px;
        }
        .activity-item:last-child {
            border-bottom: none;
        }
        .activity-item .time {
            color: #888;
            font-size: 11px;
        }
        .activity-item .title {
            color: #fff;
            margin: 5px 0;
        }
        .activity-item .detail {
            color: #aaa;
            font-size: 12px;
        }
        .log-viewer {
            background: #0a0a0a;
            border-radius: 8px;
            padding: 15px;
            font-family: 'Monaco', 'Menlo', monospace;
            font-size: 12px;
            max-height: 400px;
            overflow-y: auto;
        }
        .log-line {
            line-height: 1.6;
            white-space: pre-wrap;
            word-break: break-all;
        }
        .log-warn { color: #ffa502; }
        .log-error { color: #ff4757; }
        .log-success { color: #00ff88; }
        .log-info { color: #00d4ff; }

        .chart-container {
            position: relative;
            height: 200px;
        }

        @keyframes pulse {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.5; }
        }
        .loading {
            animation: pulse 1.5s infinite;
        }

        .refresh-btn {
            background: #00d4ff;
            color: #000;
            border: none;
            padding: 10px 20px;
            border-radius: 8px;
            cursor: pointer;
            font-weight: bold;
        }
        .refresh-btn:hover {
            background: #00ff88;
        }
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>EroASMR Scraper Dashboard</h1>
            <div>
                <button class="refresh-btn" onclick="refreshStats()">Refresh</button>
                <span class="last-updated" id="lastUpdated">Loading...</span>
            </div>
        </header>

        <div class="grid">
            <!-- Download Progress -->
            <div class="card">
                <h2>Download Progress</h2>
                <div class="stat-value" id="completedCount">-</div>
                <div class="stat-label">of <span id="totalCount">-</span> videos completed</div>
                <div class="progress-bar">
                    <div class="progress-fill" id="downloadProgress" style="width: 0%"></div>
                </div>
                <div class="progress-text" id="downloadPercent">0% complete</div>
                <div class="stats-grid">
                    <div class="mini-stat">
                        <div class="mini-stat-value status-downloading" id="downloadingCount">-</div>
                        <div class="mini-stat-label">Downloading</div>
                    </div>
                    <div class="mini-stat">
                        <div class="mini-stat-value status-pending" id="pendingCount">-</div>
                        <div class="mini-stat-label">Pending</div>
                    </div>
                    <div class="mini-stat">
                        <div class="mini-stat-value status-failed" id="failedCount">-</div>
                        <div class="mini-stat-label">Failed</div>
                    </div>
                </div>
            </div>

            <!-- Upload Progress -->
            <div class="card">
                <h2>Telegram Uploads</h2>
                <div class="stat-value status-completed" id="telegramUploads">-</div>
                <div class="stat-label">files uploaded to Telegram</div>
                <div class="chart-container" style="margin-top: 20px;">
                    <canvas id="uploadChart"></canvas>
                </div>
            </div>

            <!-- Disk Space -->
            <div class="card">
                <h2>Disk Space</h2>
                <div class="stat-value" id="diskFree">-</div>
                <div class="stat-label">GB free (<span id="diskFreePercent">-</span>%)</div>
                <div class="progress-bar">
                    <div class="progress-fill" id="diskProgress" style="width: 0%; background: linear-gradient(90deg, #00ff88, #ffa502);"></div>
                </div>
                <div class="progress-text"><span id="diskUsed">-</span> GB used of <span id="diskTotal">-</span> GB</div>
            </div>
        </div>

        <div class="grid">
            <!-- Recent Downloads -->
            <div class="card">
                <h2>Recent Downloads</h2>
                <div class="activity-list" id="recentDownloads">
                    <div class="activity-item">Loading...</div>
                </div>
            </div>

            <!-- Recent Uploads -->
            <div class="card">
                <h2>Recent Telegram Uploads</h2>
                <div class="activity-list" id="recentUploads">
                    <div class="activity-item">Loading...</div>
                </div>
            </div>

            <!-- Recent Failures -->
            <div class="card">
                <h2>Recent Failures</h2>
                <div class="activity-list" id="recentFailures">
                    <div class="activity-item">No failures</div>
                </div>
            </div>
        </div>

        <!-- Activity Log -->
        <div class="card">
            <h2>Activity Log</h2>
            <div class="log-viewer" id="activityLog">
                Loading...
            </div>
        </div>
    </div>

    <script>
        let uploadChart;

        function formatBytes(bytes) {
            if (!bytes) return '0 B';
            const k = 1024;
            const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
            const i = Math.floor(Math.log(bytes) / Math.log(k));
            return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
        }

        function formatTime(isoString) {
            if (!isoString) return '-';
            const date = new Date(isoString);
            return date.toLocaleString();
        }

        async function refreshStats() {
            try {
                const response = await fetch('/api/stats');
                const data = await response.json();

                // Update counts
                document.getElementById('totalCount').textContent = data.total_videos;
                document.getElementById('completedCount').textContent = data.completed;
                document.getElementById('downloadingCount').textContent = data.downloading;
                document.getElementById('pendingCount').textContent = data.pending;
                document.getElementById('failedCount').textContent = data.failed;
                document.getElementById('telegramUploads').textContent = data.telegram_uploads;

                // Calculate progress
                const processed = data.completed + data.failed;
                const progress = data.total_videos > 0 ? (processed / data.total_videos * 100) : 0;
                document.getElementById('downloadProgress').style.width = progress + '%';
                document.getElementById('downloadPercent').textContent = progress.toFixed(1) + '% complete';

                // Disk space
                document.getElementById('diskFree').textContent = data.disk_free_gb;
                document.getElementById('diskFreePercent').textContent = data.disk_free_percent;
                document.getElementById('diskUsed').textContent = data.disk_used_gb;
                document.getElementById('diskTotal').textContent = data.disk_total_gb;
                document.getElementById('diskProgress').style.width = (100 - data.disk_free_percent) + '%';

                // Last updated
                document.getElementById('lastUpdated').textContent = 'Updated: ' + formatTime(data.last_updated);

                // Recent downloads
                const downloadsHtml = data.recent_downloads.length > 0
                    ? data.recent_downloads.map(d => `
                        <div class="activity-item">
                            <div class="time">${formatTime(d.downloaded_at)}</div>
                            <div class="title">${d.title}</div>
                            <div class="detail">${d.file_size_mb} MB</div>
                        </div>
                    `).join('')
                    : '<div class="activity-item">No downloads yet</div>';
                document.getElementById('recentDownloads').innerHTML = downloadsHtml;

                // Recent uploads
                const uploadsHtml = data.recent_uploads.length > 0
                    ? data.recent_uploads.map(u => `
                        <div class="activity-item">
                            <div class="time">${formatTime(u.uploaded_at)}</div>
                            <div class="title">${u.title}</div>
                            <div class="detail">
                                <a href="${u.location_url}" target="_blank" style="color: #00d4ff;">View on Telegram</a>
                            </div>
                        </div>
                    `).join('')
                    : '<div class="activity-item">No uploads yet</div>';
                document.getElementById('recentUploads').innerHTML = uploadsHtml;

                // Recent failures
                const failuresHtml = data.recent_failures.length > 0
                    ? data.recent_failures.map(f => `
                        <div class="activity-item">
                            <div class="title" style="color: #ff4757;">${f.title}</div>
                            <div class="detail">${f.error || 'Unknown error'}</div>
                        </div>
                    `).join('')
                    : '<div class="activity-item">No failures</div>';
                document.getElementById('recentFailures').innerHTML = failuresHtml;

                // Update chart
                updateChart(data);

            } catch (error) {
                console.error('Failed to fetch stats:', error);
            }
        }

        function updateChart(data) {
            const ctx = document.getElementById('uploadChart').getContext('2d');

            if (uploadChart) {
                uploadChart.data.datasets[0].data = [data.completed, data.telegram_uploads, data.failed];
                uploadChart.update();
                return;
            }

            uploadChart = new Chart(ctx, {
                type: 'doughnut',
                data: {
                    labels: ['Downloaded', 'Uploaded to Telegram', 'Failed'],
                    datasets: [{
                        data: [data.completed, data.telegram_uploads, data.failed],
                        backgroundColor: ['#00d4ff', '#00ff88', '#ff4757'],
                        borderWidth: 0
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                        legend: {
                            display: false
                        }
                    }
                }
            });
        }

        async function refreshActivity() {
            try {
                const response = await fetch('/api/activity?limit=100');
                const data = await response.json();

                const logHtml = data.activity.map(line => {
                    let className = '';
                    if (line.includes('ERROR') || line.includes('Failed')) className = 'log-error';
                    else if (line.includes('WARNING')) className = 'log-warn';
                    else if (line.includes('Success') || line.includes('completed')) className = 'log-success';
                    else if (line.includes('INFO') || line.includes('Starting')) className = 'log-info';
                    return `<div class="log-line ${className}">${escapeHtml(line)}</div>`;
                }).join('');

                document.getElementById('activityLog').innerHTML = logHtml || 'No activity log';
            } catch (error) {
                console.error('Failed to fetch activity:', error);
            }
        }

        function escapeHtml(text) {
            const div = document.createElement('div');
            div.textContent = text;
            return div.innerHTML;
        }

        // Initial load
        refreshStats();
        refreshActivity();

        // Auto refresh every 10 seconds
        setInterval(refreshStats, 10000);
        setInterval(refreshActivity, 5000);
    </script>
</body>
</html>
"""
    return HTMLResponse(content=html_content)


def run_dashboard(host: str = "0.0.0.0", port: int = 8080):
    """Run the dashboard server."""
    import uvicorn
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    run_dashboard()
