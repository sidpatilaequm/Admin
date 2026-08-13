import pandas as pd
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

def clean_int_str(val):
    if val is None or pd.isna(val) or val == "":
        return ""
    try:
        # Convert float with .0 to int string, otherwise keep as is
        f = float(val)
        if f.is_integer():
            return str(int(f))
        return str(f)
    except (ValueError, TypeError):
        return str(val).strip()

def format_date_str(date_val):
    if date_val is None or pd.isna(date_val) or date_val == "":
        return ""
    if isinstance(date_val, datetime):
        return date_val.strftime("%d %b %Y")
    # If standard pandas timestamp
    if hasattr(date_val, "strftime"):
        return date_val.strftime("%d %b %Y")
    
    date_str = str(date_val).strip()
    if not date_str:
        return ""
    
    # Remove time portion if present (e.g. "2026-05-01 00:00:00")
    date_str = date_str.split(" ")[0]
    
    # Try different standard date formats
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%m/%d/%Y", "%Y/%m/%d", "%d.%m.%Y"):
        try:
            dt = datetime.strptime(date_str, fmt)
            return dt.strftime("%d %b %Y")
        except ValueError:
            continue
            
    return date_str

def parse_pr_excel(file_path_or_bytes):
    """
    Parses a PR Excel file and returns a list of dictionaries.
    """
    try:
        df = pd.read_excel(file_path_or_bytes)
        
        # Standardize column names to lowercase/underlines
        df.columns = [str(c).strip().lower().replace(" ", "_") for c in df.columns]
        
        # Replace NaN/None with empty string or default
        df = df.fillna("")
        
        pr_items = []
        for idx, row in df.iterrows():
            item = {
                "vendor_id": clean_int_str(row.get("vendor_id", "")),
                "vendor_name": str(row.get("vendor_name", "")).strip(),
                "pr_number": clean_int_str(row.get("pr_number", "")),
                "pr_status": str(row.get("pr_status", "")).strip().upper(),
                "created_by": str(row.get("created_by", "")).strip(),
                "created_date": str(row.get("created_date", "")).strip(),
                "material_number": clean_int_str(row.get("material_number", "")),
                "material_description": str(row.get("material_description", "")).strip(),
                "hsn_sac_code": clean_int_str(row.get("hsn_sac_code", "")),
                "quantity": clean_int_str(row.get("quantity", 0)),
                "uom": str(row.get("uom", "")).strip(),
                "delivery_date": str(row.get("delivery_date", "")).strip(),
                "plant": str(row.get("plant", "")).strip(),
                "fixed_vendor": str(row.get("fixed_vendor", "")).strip(),
                "account_assignment": str(row.get("account_assignment", "")).strip(),
                "gl_account": clean_int_str(row.get("gl_account", "")),
                "item_status": str(row.get("item_status", "")).strip().upper(),
                "header_notes": str(row.get("header_notes", "")).strip()
            }
            
            # Format dates nicely
            item["created_date_formatted"] = format_date_str(item["created_date"])
            item["delivery_date_formatted"] = format_date_str(item["delivery_date"])
            
            # Map status slugs and badges for UI compatibility
            status = item["pr_status"]
            if "RELEASE" in status:
                item["status_slug"] = "released"
                item["status_badge"] = "success"
                item["pr_status_display"] = "Released"
            elif "PROCESS" in status:
                item["status_slug"] = "in-process"
                item["status_badge"] = "warning"
                item["pr_status_display"] = "In Process"
            elif "OPEN" in status:
                item["status_slug"] = "open"
                item["status_badge"] = "info"
                item["pr_status_display"] = "Open"
            else:
                item["status_slug"] = "open"
                item["status_badge"] = "secondary"
                item["pr_status_display"] = item["pr_status"].title() if item["pr_status"] else "Open"
                
            pr_items.append(item)
            
        logger.info(f"Successfully parsed {len(pr_items)} PR items from Excel")
        return pr_items
        
    except Exception as e:
        logger.error(f"Error parsing PR Excel: {str(e)}")
        raise e

def parse_po_excel(file_path_or_bytes):
    """
    Parses a PO Excel file and returns a list of dictionaries.
    """
    try:
        df = pd.read_excel(file_path_or_bytes)
        df.columns = [str(c).strip().lower().replace(" ", "_") for c in df.columns]
        df = df.fillna("")
        
        po_items = []
        for idx, row in df.iterrows():
            item = {
                "vendor_id": clean_int_str(row.get("vendor_id", "")),
                "vendor_code": str(row.get("vendor_code", "")).strip(),
                "vendor_name": str(row.get("vendor_name", "")).strip(),
                "po_number": clean_int_str(row.get("po_number", "")),
                "po_date": str(row.get("po_date", "")).strip(),
                "po_type": str(row.get("po_type", "")).strip(),
                "company_code": clean_int_str(row.get("company_code", "")),
                "company_name": str(row.get("company_name", "")).strip(),
                "currency": str(row.get("currency", "")).strip(),
                "payment_terms": str(row.get("payment_terms", "")).strip(),
                "po_status": str(row.get("po_status", "")).strip(),
                "delivery_address": str(row.get("delivery_address", "")).strip(),
                "goods_receipt_plant": str(row.get("goods_receipt_plant", "")).strip(),
                "requested_delivery_date": str(row.get("requested_delivery_date", "")).strip(),
                "shipping_instructions": str(row.get("shipping_instructions", "")).strip(),
                "line_number": clean_int_str(row.get("line_number", "")),
                "material_number": str(row.get("material_number", "")).strip(),
                "material_description": str(row.get("material_description", "")).strip(),
                "quantity": clean_int_str(row.get("quantity", 0)),
                "uom": str(row.get("uom", "")).strip(),
                "net_price": clean_int_str(row.get("net_price", 0)),
                "net_value": clean_int_str(row.get("net_value", 0)),
                "tax_percent": clean_int_str(row.get("tax_percent", 0)),
                "tax_amount": clean_int_str(row.get("tax_amount", 0)),
                "total_value": clean_int_str(row.get("total_value", 0)),
                "confirm_delivery_date": str(row.get("confirm_delivery_date", "")).strip(),
                "gstin": str(row.get("gstin", "")).strip()
            }
            
            item["po_date_formatted"] = format_date_str(item["po_date"])
            item["requested_delivery_date_formatted"] = format_date_str(item["requested_delivery_date"])
            item["confirm_delivery_date_formatted"] = format_date_str(item["confirm_delivery_date"])
            
            # Map status slugs
            status = item["po_status"].upper()
            if "ACKNOWLEDGEMENT" in status:
                item["status_slug"] = "awaiting_acknowledgement"
                item["status_badge"] = "warning"
                item["po_status_display"] = "Awaiting Acknowledgement"
            elif "RELEASED" in status:
                item["status_slug"] = "released"
                item["status_badge"] = "success"
                item["po_status_display"] = "Released"
            elif "TRANSIT" in status:
                item["status_slug"] = "in_transit"
                item["status_badge"] = "info"
                item["po_status_display"] = "In Transit"
            elif "CLOSED" in status:
                item["status_slug"] = "closed"
                item["status_badge"] = "secondary"
                item["po_status_display"] = "Closed"
            else:
                item["status_slug"] = "open"
                item["status_badge"] = "secondary"
                item["po_status_display"] = item["po_status"].title() if item["po_status"] else "Open"
                
            po_items.append(item)
            
        logger.info(f"Successfully parsed {len(po_items)} PO items from Excel")
        return po_items
        
    except Exception as e:
        logger.error(f"Error parsing PO Excel: {str(e)}")
        raise e

def parse_subcon_po_excel(file_path_or_bytes):
    """
    Parses a Subcontracting PO Excel file and returns a list of dictionaries.
    """
    try:
        df = pd.read_excel(file_path_or_bytes)
        df.columns = [str(c).strip().lower().replace(" ", "_") for c in df.columns]
        df = df.fillna("")
        
        subcon_pos = []
        for idx, row in df.iterrows():
            item = {
                "vendor_id": clean_int_str(row.get("vendor_id", "")),
                "vendor_code": str(row.get("vendor_code", "")).strip(),
                "vendor_name": str(row.get("vendor_name", "")).strip(),
                "subcon_po_number": clean_int_str(row.get("subcon_po_number", "")),
                "po_status": str(row.get("po_status", "")).strip(),
                "po_date": str(row.get("po_date", "")).strip(),
                "company_code": clean_int_str(row.get("company_code", "")),
                "company_name": str(row.get("company_name", "")).strip(),
                "currency": str(row.get("currency", "")).strip(),
                "payment_terms": str(row.get("payment_terms", "")).strip(),
                "incoterms": str(row.get("incoterms", "")).strip(),
                
                # FG details
                "fg_line_item_no": clean_int_str(row.get("fg_line_item_no", "")),
                "fg_material_number": str(row.get("fg_material_number", "")).strip(),
                "fg_description": str(row.get("fg_description", "")).strip(),
                "fg_ordered_qty": clean_int_str(row.get("fg_ordered_qty", 0)),
                "fg_uom": str(row.get("fg_uom", "")).strip(),
                "processing_charge_per_unit": clean_int_str(row.get("processing_charge_per_unit", 0)),
                "total_processing_value": clean_int_str(row.get("total_processing_value", 0)),
                "required_delivery_date": str(row.get("required_delivery_date", "")).strip(),
                
                # Component details
                "component_line_no": str(row.get("component_line_no", "")).strip(),
                "component_material_no": str(row.get("component_material_no", "")).strip(),
                "component_description": str(row.get("component_description", "")).strip(),
                "required_qty_per_unit": str(row.get("required_qty_per_unit", "")).strip(),
                "total_issued_qty": str(row.get("total_issued_qty", "")).strip(),
                "stock_at_vendor": str(row.get("stock_at_vendor", "")).strip(),
                "total_stock_capacity": str(row.get("total_stock_capacity", "")).strip(),
                "component_uom": str(row.get("component_uom", "")).strip(),
                "scrap_percent": str(row.get("scrap_percent", "")).strip(),
                
                # Movement Details
                "movement_doc_number": str(row.get("movement_doc_number", "")).strip(),
                "movement_type": clean_int_str(row.get("movement_type", "")),
                "movement_description": str(row.get("movement_description", "")).strip(),
                "movement_material": str(row.get("movement_material", "")).strip(),
                "movement_qty": str(row.get("movement_qty", "")).strip(),
                "movement_date": str(row.get("movement_date", "")).strip(),
            }
            
            item["po_date_formatted"] = format_date_str(item["po_date"])
            item["required_delivery_date_formatted"] = format_date_str(item["required_delivery_date"])
            item["movement_date_formatted"] = format_date_str(item["movement_date"])
            
            # Map status slugs
            status = item["po_status"].upper()
            if "IN PROCESS" in status:
                item["status_slug"] = "in_process"
                item["status_badge"] = "info"
                item["po_status_display"] = "In Process"
            elif "RELEASED" in status:
                item["status_slug"] = "released"
                item["status_badge"] = "success"
                item["po_status_display"] = "Released"
            elif "CLOSED" in status:
                item["status_slug"] = "closed"
                item["status_badge"] = "secondary"
                item["po_status_display"] = "Closed"
            else:
                item["status_slug"] = "open"
                item["status_badge"] = "secondary"
                item["po_status_display"] = item["po_status"].title() if item["po_status"] else "Open"
                
            subcon_pos.append(item)
            
        logger.info(f"Successfully parsed {len(subcon_pos)} Subcon PO items from Excel")
        return subcon_pos
        
    except Exception as e:
        logger.error(f"Error parsing Subcon PO Excel: {str(e)}")
        raise e

def parse_service_po_excel(file_path):
    """
    Parses a Service PO Excel file with multiple tabs or a flattened structure.
    Groups Service Lines and SES History under each distinct Service PO number.
    """
    try:
        df = pd.read_excel(file_path)
        
        # Clean column names
        df.columns = df.columns.str.strip().str.lower().str.replace(' ', '_')
        
        service_po_map = {}
        
        for index, row in df.iterrows():
            po_num = str(row.get('service_po_number', '')).strip()
            if not po_num or po_num == 'nan':
                continue
                
            def _safe_float(val):
                try:
                    return float(val) if val and not pd.isna(val) else 0.0
                except (ValueError, TypeError):
                    return 0.0

            # If this is the first time we see this PO, initialize the Header & Vendor details
            if po_num not in service_po_map:
                service_po_map[po_num] = {
                    "service_po_number": po_num,
                    "po_status": str(row.get('po_status', '')).strip(),
                    "po_date": format_date_str(row.get('po_date')),
                    "po_date_formatted": format_date_str(row.get('po_date')),
                    "service_period_from": format_date_str(row.get('service_period_from')),
                    "service_period_to": format_date_str(row.get('service_period_to')),
                    "company_code": str(row.get('company_code', '')).strip(),
                    "company_name": str(row.get('company_name', '')).strip(),
                    "currency": str(row.get('currency', '')).strip(),
                    "payment_terms": str(row.get('payment_terms', '')).strip(),
                    
                    "vendor_id": str(row.get('vendor_id', '')).strip(),
                    "vendor_code": str(row.get('vendor_code', '')).strip(),
                    "vendor_name": str(row.get('vendor_name', '')).strip(),
                    "vendor_address": str(row.get('vendor_address', '')).strip(),
                    "gst_number": str(row.get('gst_number', '')).strip(),
                    "pan_number": str(row.get('pan_number', '')).strip(),
                    
                    "service_lines": [],
                    "ses_history": [],
                    "total_net_value": 0,
                    
                    "status_badge": "warning", # default
                    "po_status_display": "Pending"
                }
                
                # Setup Status
                status = service_po_map[po_num]["po_status"].upper()
                if "PENDING" in status:
                    service_po_map[po_num]["status_slug"] = "pending"
                    service_po_map[po_num]["status_badge"] = "warning"
                    service_po_map[po_num]["po_status_display"] = "SES Pending"
                elif "APPROVED" in status:
                    service_po_map[po_num]["status_slug"] = "approved"
                    service_po_map[po_num]["status_badge"] = "success"
                    service_po_map[po_num]["po_status_display"] = "Approved"
                else:
                    service_po_map[po_num]["status_slug"] = "open"
                    service_po_map[po_num]["status_badge"] = "secondary"
                    service_po_map[po_num]["po_status_display"] = service_po_map[po_num]["po_status"].title() if service_po_map[po_num]["po_status"] else "Open"
            
            po_data = service_po_map[po_num]
            
            # Extract Service Line Data
            line_num = str(row.get('line_number', '')).strip()
            if line_num and line_num != 'nan':
                # Check for duplicate line number
                if not any(comp['line_no'] == line_num for comp in po_data['service_lines']):
                    qty = _safe_float(row.get('quantity'))
                    rate = _safe_float(row.get('rate'))
                    net_val = _safe_float(row.get('net_value'))
                    
                    po_data['service_lines'].append({
                        "line_no": line_num,
                        "service_no": str(row.get('service_number', '')).strip(),
                        "description": str(row.get('service_description', '')).strip(),
                        "quantity": f"{qty:g}" if qty else "0",
                        "uom": str(row.get('uom', '')).strip(),
                        "rate": f"{rate:,.2f}" if rate else "0.00",
                        "net_value": f"{net_val:,.2f}" if net_val else "0.00",
                        "net_value_raw": net_val,
                        "cost_centre": str(row.get('cost_centre', '')).strip()
                    })
            
            # Extract SES History Data
            ses_num = str(row.get('ses_number', '')).strip()
            if ses_num and ses_num != 'nan':
                # Check for duplicate SES doc
                if not any(mvt['ses_number'] == ses_num for mvt in po_data['ses_history']):
                    ses_status = str(row.get('ses_status', '')).strip()
                    badge_color = "success" if "APPROVED" in ses_status.upper() else "warning"
                    
                    po_data['ses_history'].append({
                        "ses_number": ses_num,
                        "ses_month": str(row.get('ses_month', '')).strip(),
                        "ses_status": ses_status,
                        "badge_color": badge_color
                    })
                    
        # Final aggregation
        service_pos = []
        for po_num, item in service_po_map.items():
            # Calculate total net value dynamically
            total_val = sum(line.get('net_value_raw', 0) for line in item['service_lines'])
            item['total_net_value'] = f"{total_val:,.2f}"
            item['total_net_value_raw'] = total_val
            
            # Sort lists (optional)
            item['service_lines'] = sorted(item['service_lines'], key=lambda x: str(x['line_no']))
            item['ses_history'] = sorted(item['ses_history'], key=lambda x: str(x['ses_number']))
            
            service_pos.append(item)
            
        logger.info(f"Successfully parsed {len(service_pos)} Service PO items from Excel")
        return service_pos
        
    except Exception as e:
        logger.error(f"Error parsing Service PO Excel: {str(e)}")
        raise e

def parse_payment_excel(file_path):
    """
    Parses a Vendor Payments Excel file and returns a list of dictionaries.
    """
    try:
        df = pd.read_excel(file_path)
        
        # Clean column names
        df.columns = df.columns.str.strip().str.lower().str.replace(' ', '_').str.replace('/', '')
        
        payments = []
        
        for index, row in df.iterrows():
            doc_num = str(row.get('document_number', '')).strip()
            if not doc_num or doc_num == 'nan':
                continue
                
            def _safe_float(val):
                try:
                    return float(val) if val and not pd.isna(val) else 0.0
                except (ValueError, TypeError):
                    return 0.0
            
            gross = _safe_float(row.get('gross_amount'))
            tds = _safe_float(row.get('tds_deducted'))
            net = _safe_float(row.get('net_paid'))
            
            status = str(row.get('payment_status', '')).strip().upper()
            if "PAID" in status:
                status_slug = "paid"
                status_badge = "success"
                status_display = "Paid"
            elif "IN PROCESS" in status:
                status_slug = "in_process"
                status_badge = "info"
                status_display = "In Process"
            elif "PENDING" in status:
                status_slug = "pending"
                status_badge = "warning"
                status_display = "Pending"
            elif "PARTIAL" in status:
                status_slug = "partial"
                status_badge = "warning"
                status_display = "Partial"
            else:
                status_slug = "open"
                status_badge = "secondary"
                status_display = status.title() if status else "Open"
                
            payment_method = str(row.get('payment_method', '')).strip().upper()
            method_icon = "ri-bank-line"
            if "RTGS" in payment_method:
                method_icon = "ri-bank-line"
            elif "NEFT" in payment_method:
                method_icon = "ri-exchange-line"
            elif "CHEQUE" in payment_method:
                method_icon = "ri-booklet-line"
            
            payment = {
                "vendor_code": str(row.get('vendor_code', '')).strip(),
                "vendor_name": str(row.get('vendor_name', '')).strip(),
                "document_number": doc_num,
                "fiscal_year": str(row.get('fiscal_year', '')).strip(),
                "invoice_reference": str(row.get('invoice_reference', '')).strip(),
                "invoice_date": format_date_str(row.get('invoice_date')),
                "payment_date": format_date_str(row.get('payment_date')),
                
                "gross_amount": f"{gross:,.2f}",
                "gross_amount_raw": gross,
                "tds_deducted": f"{tds:,.2f}" if tds else "—",
                "tds_deducted_raw": tds,
                "net_paid": f"{net:,.2f}",
                "net_paid_raw": net,
                
                "payment_method": payment_method,
                "method_icon": method_icon,
                "utr_cheque_number": str(row.get('utr__cheque_number', str(row.get('utr_cheque_number', '')))).strip(),
                "house_bank": str(row.get('house_bank', '')).strip(),
                
                "status_slug": status_slug,
                "status_badge": status_badge,
                "status_display": status_display,
                
                "company_code": str(row.get('company_code', '')).strip(),
                "currency": str(row.get('currency', '')).strip(),
                "overdue_days": str(row.get('overdue_days', '')).strip(),
                "sync_timestamp": str(row.get('sync_timestamp', '')).strip(),
                
                "doc_type": str(row.get('doc_type', '')).strip(),
                "reconciliation_account": str(row.get('reconciliation_account', '')).strip(),
                "payment_run_date": format_date_str(row.get('payment_run_date')),
                "payment_run_id": str(row.get('payment_run_id', '')).strip(),
                "beneficiary_name": str(row.get('beneficiary_name', '')).strip(),
                "account_number": str(row.get('account_number', '')).strip(),
                "ifsc_code": str(row.get('ifsc_code', '')).strip(),
                "bank_name": str(row.get('bank_name', '')).strip(),
                "branch_name": str(row.get('branch_name', '')).strip(),
                "penny_drop_status": str(row.get('penny_drop_status', '')).strip(),
                "timeline_invoice_posted": str(row.get('timeline_invoice_posted', '')).strip(),
                "timeline_payment_proposal": str(row.get('timeline_payment_proposal', '')).strip(),
                "timeline_tds_deducted": str(row.get('timeline_tds_deducted', '')).strip(),
                "timeline_bank_transfer": str(row.get('timeline_bank_transfer', '')).strip(),
                "timeline_payment_confirmed": str(row.get('timeline_payment_confirmed', '')).strip(),
                "sap_raw_response": str(row.get('sap_raw_response', '')).strip()
            }
            
            payments.append(payment)
            
        logger.info(f"Successfully parsed {len(payments)} Vendor Payment items from Excel")
        return payments
        
    except Exception as e:
        logger.error(f"Error parsing Vendor Payments Excel: {str(e)}")
        raise e
