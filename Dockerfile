FROM frappe/erpnext:v15

ARG BRANCH=main

USER frappe

# ENG-643: bake assets/admin_panel into the image. In k8s, sites/ is a PVC and
# sites/assets symlinks to this image dir, so every pod must carry the link
# itself (the after_migrate heal only writes into the short-lived migrate pod).
# The test lines fail the build if the link is missing, is a real directory,
# or does not resolve to the app's public JS.
RUN bench get-app admin-panel --branch ${BRANCH} https://github.com/lnflash/frappe-flash-admin && \
    bench build --apps admin_panel && \
    ln -sfn /home/frappe/frappe-bench/apps/admin_panel/admin_panel/public /home/frappe/frappe-bench/assets/admin_panel && \
    test -L /home/frappe/frappe-bench/assets/admin_panel && \
    test -f /home/frappe/frappe-bench/assets/admin_panel/js/back_to_dashboard.js
