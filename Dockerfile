FROM frappe/erpnext:v15

ARG BRANCH=main

USER frappe

RUN bench get-app admin-panel --branch ${BRANCH} https://github.com/lnflash/frappe-flash-admin && \
    bench build --apps admin_panel
