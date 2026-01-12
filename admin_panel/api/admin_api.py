import frappe
import requests
from .graphql_client import GraphQLClient, GraphQLError


@frappe.whitelist()
def get_account_by_phone(phone):
	"""Get account details by phone number"""
	try:
		client = GraphQLClient()
		account = client.get_account_by_phone(phone)
		
		if account is None:
			frappe.response['http_status_code'] = 404
			return {"error": "Account not found"}
		
		return account
		
	except GraphQLError as e:
		frappe.logger().error(f"GraphQL error for phone {phone}: {str(e)}")
		frappe.response['http_status_code'] = 500
		return {"error": f"GraphQL error: {str(e)}"}
		
	except requests.exceptions.RequestException as e:
		frappe.logger().error(f"Request error for phone {phone}: {str(e)}")
		frappe.response['http_status_code'] = 500
		return {"error": f"Request error: {str(e)}"}
		
	except Exception as e:
		frappe.logger().error(f"Unexpected error for phone {phone}: {str(e)}")
		frappe.response['http_status_code'] = 500
		return {"error": "An internal error occurred"}


@frappe.whitelist()
def update_account_level(uid, level):
	"""Update account level"""
	try:
		client = GraphQLClient()
		return client.update_account_level(uid, level)
		
	except Exception as e:
		frappe.logger().error(f"Error updating account {uid} to level {level}: {str(e)}")
		frappe.response['http_status_code'] = 500
		return {"error": "An internal error occurred"}


@frappe.whitelist()
def send_alert(title, message, tag="EMERGENCY"):
	"""Send broadcast alert to all users via admin API"""
	try:
		# Validate inputs
		if not title or not message:
			frappe.response['http_status_code'] = 400
			return {"error": "Title and message are required"}
		
		# Call GraphQL API
		client = GraphQLClient()
		result = client.send_broadcast_alert(title, message, tag)
		
		# Check for errors in the response
		if result.get('errors'):
			error_messages = [err.get('message', 'Unknown error') for err in result['errors']]
			frappe.logger().error(f"Broadcast alert errors: {error_messages}")
			frappe.response['http_status_code'] = 400
			return {
				"success": False,
				"errors": error_messages
			}
		
		# Success
		if result.get('success'):
			frappe.get_doc({
				"doctype": "User Alerts",
                "title": title,
                "message": message,
                "tag": tag,
                "sent_by": frappe.session.user,
                "sent_on": frappe.utils.now_datetime()
			}).insert(ignore_permissions=True)
			frappe.db.commit()
			
			return {
				"success": True,
				"message": f"Alert sent successfully: {title}"
			}
		else:
			frappe.response['http_status_code'] = 500
			return {
				"success": False,
				"error": "Failed to send alert"
			}
			
	except GraphQLError as e:
		frappe.logger().error(f"GraphQL error sending alert: {str(e)}")
		frappe.response['http_status_code'] = 500
		return {
			"success": False,
			"error": str(e)
		}
		
	except requests.exceptions.RequestException as e:
		frappe.logger().error(f"Request error sending alert: {str(e)}")
		frappe.response['http_status_code'] = 500
		return {
			"success": False,
			"error": str(e)
		}
		
	except Exception as e:
		frappe.logger().error(f"Unexpected error sending alert: {str(e)}")
		frappe.response['http_status_code'] = 500
		return {
			"success": False,
			"error": "An internal error occurred"
		}


@frappe.whitelist()
def get_user_alerts(limit=10):
    """Return latest User Alerts"""
    try:
        logs = frappe.get_all(
            "User Alerts",
            fields=["title", "message", "tag", "sent_by", "sent_on"],
            order_by="sent_on desc",
            limit_page_length=int(limit)
        )
        return {"logs": logs}
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Error fetching User Alerts")
        frappe.response["http_status_code"] = 500
        return {"error": str(e)}


@frappe.whitelist()
def get_upgrade_requests(status=None, requested_level=None):
    """Get all pending upgrade requests from Account Upgrade Request doctype"""
    try:
        filters = {}
        if status:
            filters["status"] = status

        if requested_level:
            filters["requested_level"] = requested_level

        requests = frappe.get_all(
            "Account Upgrade Request",
            filters=filters,
            fields=["*"],
            order_by="creation desc"
        )

        return requests

    except Exception as e:
        frappe.logger().error(f"Error fetching upgrade requests: {str(e)}")
        frappe.response["http_status_code"] = 500
        return {"error": "An internal error occurred"}


PhoneNumber = str
Username = str

@frappe.whitelist()
def search_account(id: PhoneNumber | Username):
    """Search account by phone number"""
    try:
        if not id:
            frappe.response['http_status_code'] = 400
            return {"error": "Phone number or Username is required"}
   
        cleaned_id = ''.join(filter(str.isdigit, id))
        if len(cleaned_id) >= 10:
            requests = frappe.get_all(
                "Account Upgrade Request",
                filters=[["phone_number", "like", f"%{id}%"]],
                fields=["*"],
                order_by="creation desc"
            )

            if requests:
                return requests
            else:
                frappe.response['http_status_code'] = 404
                return {"error": "Account not found"}
        else:
            requests = frappe.get_all(
                "Account Upgrade Request",
                filters=[["username", "like", f"%{id}%"]],
                fields=["*"],
                order_by="creation desc"
            )
    
            if requests:
                return requests
            else:
                frappe.response['http_status_code'] = 404
                return {"error": "Account not found"}
        

    except Exception as e:
        frappe.logger().error(f"Error searching account: {str(e)}")
        frappe.response['http_status_code'] = 500
        return {"error": "An internal error occurred"}

@frappe.whitelist()
def approve_upgrade_request(request_id):
    req = frappe.get_doc("Account Upgrade Request", request_id)

    req.status = "Approved"
    req.approved_by = frappe.session.user
    req.approval_date = frappe.utils.now_datetime()
    req.save()

    frappe.db.commit()

    return {"success": True, "message": "Request approved and user level updated."}

@frappe.whitelist()
def reject_upgrade_request(request_id, reason=None):
    req = frappe.get_doc("Account Upgrade Request", request_id)

    req.status = "Rejected"
    req.rejection_reason = reason or "No reason provided"
    req.approved_by = frappe.session.user  # store the person who rejected
    req.approval_date = frappe.utils.now_datetime()
    req.save()

    frappe.db.commit()

    return {"success": True, "message": "Request rejected."}



@frappe.whitelist()
def get_cashout_requests(status=None, currency=None):
    try:

        data = get_user_bank_details("nick")
        print(data)
        return [{
            "order_id": "1234-9876-4567",
            "offer_id": "1234-9876-4567",
            "username": "nick", 
            "send_amount": 45, 
            "send_currency": "USD", 
            "receive_amount": 7216.21,  
            "currency": "JMD",
            "expiration_time": 12341123123,
            "status": "Pending",
            "flash_fee": 2,
            "exchange_rate": 160.36,
            **data}]

        filters = {}
        
        if status:
            filters['docstatus'] = 0 if status == "Pending" else 1 if status == "Completed" else 2
        
        if currency:
            filters['currency'] = currency
        
        journal_entries = frappe.get_all(
            'Journal Entry',
            filters=filters,
            fields=[
                'name',
                'posting_date as creation',
                'user_remark as order_id',
                'total_debit as send_amount',
                'total_credit as receive_amount',
                'custom_username as username',
                'custom_phone as phone_number',
                'custom_currency as currency',
                'custom_send_currency as send_currency',
                'custom_expiration_time as expiration_time',
                'custom_status as status',
                'docstatus'
            ],
            order_by='creation desc'
        )
        
        payment_entries = frappe.get_all(
            'Payment Entry',
            filters=filters,
            fields=[
                'name',
                'posting_date as creation',
                'reference_no as order_id',
                'paid_amount as send_amount',
                'received_amount as receive_amount',
                'custom_username as username',
                'custom_phone as phone_number',
                'paid_to_account_currency as currency',
                'paid_from_account_currency as send_currency',
                'custom_expiration_time as expiration_time',
                'custom_status as status',
                'docstatus'
            ],
            order_by='creation desc'
        )
        
        # Combine both lists
        all_requests = journal_entries + payment_entries
        
        # Enrich with user details and bank info
        for req in all_requests:
            # Get user details from Account Upgrade Request
            user_details = get_user_bank_details(req.get('username'))
            if user_details:
                req.update(user_details)
            
            # Calculate additional fields if needed
            req['offer_id'] = req.get('name')  # Or fetch from custom field
            req['exchange_rate'] = calculate_exchange_rate(
                req.get('send_amount'), 
                req.get('receive_amount')
            )
            req['flash_fee'] = calculate_flash_fee(req.get('send_amount'))
        
        return all_requests
        
    except Exception as e:
        frappe.log_error(f"Error fetching cashout requests: {str(e)}")
        frappe.throw(_("Failed to load cashout requests"))


@frappe.whitelist()
def search_cashout(query):
    """
    Search cashout requests by order ID or username
    """
    try:
        # Search in Journal Entry
        journal_filters = [
            ['Journal Entry', 'user_remark', 'like', f'%{query}%'],
            ['Journal Entry', 'custom_username', 'like', f'%{query}%']
        ]
        
        journal_entries = frappe.get_all(
            'Journal Entry',
            filters=journal_filters,
            fields=[
                'name',
                'posting_date as creation',
                'user_remark as order_id',
                'total_debit as send_amount',
                'total_credit as receive_amount',
                'custom_username as username',
                'custom_phone as phone_number',
                'custom_currency as currency',
                'custom_send_currency as send_currency',
                'custom_expiration_time as expiration_time',
                'custom_status as status',
                'docstatus'
            ],
            or_filters=journal_filters,
            order_by='creation desc',
            limit=20
        )
        
        # Search in Payment Entry
        payment_filters = [
            ['Payment Entry', 'reference_no', 'like', f'%{query}%'],
            ['Payment Entry', 'custom_username', 'like', f'%{query}%']
        ]
        
        payment_entries = frappe.get_all(
            'Payment Entry',
            filters=payment_filters,
            fields=[
                'name',
                'posting_date as creation',
                'reference_no as order_id',
                'paid_amount as send_amount',
                'received_amount as receive_amount',
                'custom_username as username',
                'custom_phone as phone_number',
                'paid_to_account_currency as currency',
                'paid_from_account_currency as send_currency',
                'custom_expiration_time as expiration_time',
                'custom_status as status',
                'docstatus'
            ],
            or_filters=payment_filters,
            order_by='creation desc',
            limit=20
        )
        
        # Combine results
        all_results = journal_entries + payment_entries
        
        # Enrich with user details
        for req in all_results:
            user_details = get_user_bank_details(req.get('username'))
            if user_details:
                req.update(user_details)
            
            req['offer_id'] = req.get('name')
            req['exchange_rate'] = calculate_exchange_rate(
                req.get('send_amount'), 
                req.get('receive_amount')
            )
            req['flash_fee'] = calculate_flash_fee(req.get('send_amount'))
        
        return all_results
        
    except Exception as e:
        frappe.log_error(f"Error searching cashout requests: {str(e)}")
        frappe.throw(_("Search failed"))


@frappe.whitelist()
def confirm_cashout_payment(request_id, confirmation_code):
    """
    Confirm cashout payment by creating a Payment Entry
    """
    try:
        # Validate confirmation code
        if not confirmation_code:
            frappe.throw(_("Confirmation code is required"))
        
        # Get the original request (could be Journal Entry or Payment Entry)
        journal_entry = frappe.db.exists('Journal Entry', request_id)
        
        if journal_entry:
            # Get Journal Entry details
            je = frappe.get_doc('Journal Entry', request_id)
            
            # Create Payment Entry
            payment_entry = frappe.new_doc('Payment Entry')
            payment_entry.payment_type = 'Pay'
            payment_entry.posting_date = nowdate()
            payment_entry.company = je.company or frappe.defaults.get_user_default('company')
            
            # Set accounts (adjust these based on your account structure)
            payment_entry.paid_from = get_default_bank_account()
            payment_entry.paid_to = get_user_bank_account(je.custom_username)
            
            # Set amounts
            payment_entry.paid_amount = je.total_debit
            payment_entry.received_amount = je.total_credit
            payment_entry.source_exchange_rate = 1
            payment_entry.target_exchange_rate = calculate_exchange_rate(
                je.total_debit, je.total_credit
            )
            
            # Set custom fields
            payment_entry.custom_username = je.custom_username
            payment_entry.custom_confirmation_code = confirmation_code
            payment_entry.reference_no = je.user_remark  # order_id
            payment_entry.reference_date = nowdate()
            
            # Set party (if applicable)
            if je.custom_username:
                customer = get_customer_by_username(je.custom_username)
                if customer:
                    payment_entry.party_type = 'Customer'
                    payment_entry.party = customer
            
            # Save and submit
            payment_entry.insert(ignore_permissions=True)
            payment_entry.submit()
            
            # Update Journal Entry status
            je.custom_status = 'Completed'
            je.custom_payment_entry = payment_entry.name
            je.custom_confirmation_code = confirmation_code
            je.custom_confirmed_by = frappe.session.user
            je.custom_confirmation_date = now_datetime()
            je.save(ignore_permissions=True)
            
            frappe.db.commit()
            
            return {
                'success': True,
                'message': 'Payment confirmed successfully',
                'payment_entry': payment_entry.name
            }
        else:
            frappe.throw(_("Request not found"))
            
    except Exception as e:
        frappe.log_error(f"Error confirming payment: {str(e)}")
        frappe.throw(_("Failed to confirm payment: {0}").format(str(e)))


def get_user_bank_details(username):
    """
    Get user's bank details from Account Upgrade Request
    """
    if not username:
        return {}
    
    try:
        # Get the most recent approved upgrade request for this user
        upgrade_request = frappe.get_all(
            'Account Upgrade Request',
            filters={
                'username': username,
                'status': 'Approved'
            },
            fields="*",
            order_by='modified desc',
            limit=1
        )
        
        if upgrade_request:
            return upgrade_request[0]
        
        return {}
        
    except Exception as e:
        frappe.log_error(f"Error fetching user bank details: {str(e)}")
        return {}


def calculate_exchange_rate(send_amount, receive_amount):
    """
    Calculate exchange rate between send and receive amounts
    """
    try:
        if send_amount and receive_amount:
            return float(receive_amount) / float(send_amount)
        return 0
    except:
        return 0


def calculate_flash_fee(amount):
    """
    Calculate flash fee (adjust percentage as needed)
    """
    try:
        fee_percentage = 0.02  # 2% fee
        return float(amount) * fee_percentage
    except:
        return 0


def get_default_bank_account():
    """
    Get default company bank account
    """
    # Adjust this based on your chart of accounts
    company = frappe.defaults.get_user_default('company')
    
    bank_account = frappe.db.get_value(
        'Account',
        {
            'company': company,
            'account_type': 'Bank',
            'is_group': 0
        },
        'name'
    )
    
    return bank_account or 'Cash - Company'


def get_user_bank_account(username):
    """
    Get user's bank account from system
    """
    # This might need to be adjusted based on how you store user bank accounts
    # For now, returning a placeholder
    return 'Debtors - Company'


def get_customer_by_username(username):
    """
    Get customer linked to username
    """
    customer = frappe.db.get_value(
        'Customer',
        {'custom_username': username},
        'name'
    )
    
    return customer