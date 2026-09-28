# UI Refresh Fix v2.2.3

## Fixed
- Removed the automatic `setInterval(loadAll, 12000)` dashboard refresh loop.
- Dashboard data now loads once when the page opens and only refreshes when the user clicks **Refresh** or another user action explicitly calls `loadAll()`.
- Added a refresh-in-progress guard to prevent overlapping refresh requests.
- The manual **Refresh** button now shows `Refreshing…` while the request is active and returns to `Refresh` when complete.

## Expected behavior
Waiting on the dashboard for 15–20 seconds must no longer change hive values or trigger another dashboard reload by itself.
