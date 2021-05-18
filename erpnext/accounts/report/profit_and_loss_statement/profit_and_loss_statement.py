# Copyright (c) 2015, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

from __future__ import unicode_literals
import frappe
from frappe import _
from frappe.utils import flt
from erpnext.accounts.report.financial_statements import (get_period_list, get_columns, get_data)
from erpnext.accounts.report.financial_statements import fiscal_years_periods

def execute(filters=None):
	with_sales_person = filters.group_by == "Sales Person"

	period_list = get_period_list(filters.from_fiscal_year, filters.to_fiscal_year,
		filters.periodicity, filters.accumulated_values, filters.company,
		with_sales_person=with_sales_person, start_month=filters.start_month, end_month=filters.end_month)

	income = get_data(filters.company, "Income", "Credit", period_list, filters = filters,
		accumulated_values=filters.accumulated_values, ignore_closing_entries=True,
		ignore_accumulated_values_for_fy= True, with_sales_person=with_sales_person, is_profit_and_loss=True)

	expense = get_data(filters.company, "Expense", "Debit", period_list, filters=filters,
		accumulated_values=filters.accumulated_values, ignore_closing_entries=True,
		ignore_accumulated_values_for_fy= True, with_sales_person=with_sales_person, is_profit_and_loss=True)

	net_profit_loss = get_net_profit_loss(income, expense, period_list, filters.company, filters.presentation_currency, start_month=filters.start_month, end_month=filters.end_month, is_profit_and_loss=True)

	data = []
	data.extend(income or [])
	data.extend(expense or [])
	if net_profit_loss:
		data.append(net_profit_loss)

	columns = get_columns(filters.periodicity, period_list, filters.accumulated_values, filters.company,
						  with_sales_person=with_sales_person,
						  start_month=filters.start_month, end_month=filters.end_month, is_profit_and_loss=True)

	chart = get_chart_data(filters, columns, income, expense, net_profit_loss)

	return columns, data, None, chart


def get_net_profit_loss(income, expense, period_list, company, currency=None, consolidated=False,
						start_month=None, end_month=None, is_profit_and_loss=True):
	total = 0
	net_profit_loss = {
		"account_name": "'" + _("Profit for the year") + "'",
		"account": "'" + _("Profit for the year") + "'",
		"warn_if_negative": True,
		"currency": currency or frappe.get_cached_value('Company',  company,  "default_currency")
	}

	has_value = False

	for period in period_list:
		key = period if consolidated else period.key
		total_income = flt(income[-2][key], 3) if income else 0
		total_expense = flt(expense[-2][key], 3) if expense else 0

		if start_month and end_month and is_profit_and_loss:
			fiscal_years_keys = fiscal_years_periods(period_list, start_month, end_month)
			for fiscal_year in fiscal_years_keys:
				total_income_fy = flt(income[-2][fiscal_year], 3) if income else 0
				total_expense_fy = flt(expense[-2][fiscal_year], 3) if expense else 0

				net_profit_loss[fiscal_year] = total_income_fy - total_expense_fy

				if net_profit_loss[fiscal_year]:
					has_value = True

				total += flt(net_profit_loss[fiscal_year])

		net_profit_loss[key] = total_income - total_expense

		if net_profit_loss[key]:
			has_value=True

		total += flt(net_profit_loss[key])
		net_profit_loss["total"] = total

	if has_value:
		return net_profit_loss


def get_chart_data(filters, columns, income, expense, net_profit_loss):
	labels = [d.get("label") for d in columns[2:]]

	income_data, expense_data, net_profit = [], [], []

	for p in columns[2:]:
		if income:
			income_data.append(income[-2].get(p.get("fieldname")))
		if expense:
			expense_data.append(expense[-2].get(p.get("fieldname")))
		if net_profit_loss:
			net_profit.append(net_profit_loss.get(p.get("fieldname")))

	datasets = []
	if income_data:
		datasets.append({'name': _('Income'), 'values': income_data})
	if expense_data:
		datasets.append({'name': _('Expense'), 'values': expense_data})
	if net_profit:
		datasets.append({'name': _('Net Profit/Loss'), 'values': net_profit})

	chart = {
		"data": {
			'labels': labels,
			'datasets': datasets
		}
	}

	if not filters.accumulated_values:
		chart["type"] = "bar"
	else:
		chart["type"] = "line"

	chart["fieldtype"] = "Currency"

	return chart
