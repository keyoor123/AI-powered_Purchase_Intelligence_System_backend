import os
import io
import logging
from datetime import datetime
from typing import Dict, Any, List

# Set matplotlib backend to Agg to prevent headless server GUI execution errors
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image, PageBreak, KeepTogether
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors

logger = logging.getLogger(__name__)

class PDFReportGenerator:
    def __init__(self):
        pass

    def _generate_category_chart(self, category_spending: List[Dict[str, Any]]) -> bytes:
        """Generates a category spending pie chart and returns it as png bytes."""
        if not category_spending:
            return None

        # Sort and take top 5
        sorted_cats = sorted(category_spending, key=lambda x: x.get("total_spending", 0), reverse=True)[:5]
        labels = [item["_id"] for item in sorted_cats]
        values = [item["total_spending"] for item in sorted_cats]

        # Check if there are other categories
        total_top_spent = sum(values)
        total_overall_spent = sum(item.get("total_spending", 0) for item in category_spending)
        if total_overall_spent > total_top_spent:
            labels.append("Others")
            values.append(total_overall_spent - total_top_spent)

        # Plotting
        fig, ax = plt.subplots(figsize=(6, 3.5), subplot_kw=dict(aspect="equal"))
        
        # Premium color palette: Slate, Sky, Teal, Indigo, Amber, Rose
        color_palette = ["#0f172a", "#0284c7", "#0d9488", "#4f46e5", "#d97706", "#e11d48", "#64748b"]
        colors_list = color_palette[:len(labels)]
        
        wedges, texts, autotexts = ax.pie(
            values, 
            labels=labels, 
            autopct='%1.1f%%',
            startangle=140, 
            colors=colors_list,
            textprops=dict(color="black", fontsize=9)
        )
        
        # Clean typography for autotexts
        plt.setp(autotexts, size=8, weight="bold", color="white")
        ax.set_title("Spending Distribution by Category", fontsize=12, fontweight="bold", pad=15)
        
        plt.tight_layout()
        buf = io.BytesIO()
        plt.savefig(buf, format='png', dpi=200)
        plt.close(fig)
        buf.seek(0)
        return buf.getvalue()

    def _generate_monthly_trend_chart(self, monthly_purchase_summary: List[Dict[str, Any]]) -> bytes:
        """Generates a monthly spend trend line chart and returns it as png bytes."""
        if not monthly_purchase_summary:
            return None

        # Sort chronologically by label (YYYY-MM)
        sorted_months = sorted(monthly_purchase_summary, key=lambda x: x.get("label", ""))[-6:] # last 6 months
        labels = [item["label"] for item in sorted_months]
        values = [item["total_amount"] for item in sorted_months]

        if not labels:
            return None

        fig, ax = plt.subplots(figsize=(6, 3.5))
        
        ax.plot(labels, values, marker='o', linewidth=2.5, color='#0284c7', label="Spending")
        ax.fill_between(labels, values, color='#e0f2fe', alpha=0.5)
        
        ax.set_title("Monthly Spend Trend (Last 6 Months)", fontsize=12, fontweight="bold", pad=15)
        ax.set_ylabel("Total Spent (₹)", fontsize=9, fontweight="bold")
        ax.tick_params(axis='both', labelsize=8)
        
        # Remove top and right borders
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)
        ax.grid(axis='y', linestyle='--', alpha=0.7)
        
        plt.tight_layout()
        buf = io.BytesIO()
        plt.savefig(buf, format='png', dpi=200)
        plt.close(fig)
        buf.seek(0)
        return buf.getvalue()

    def build_monthly_report_pdf(self, 
                                  user_name: str, 
                                  org_name: str, 
                                  month_label: str, 
                                  analytics_data: Dict[str, Any], 
                                  ai_summary: str) -> bytes:
        """Compiles the monthly intelligence report PDF."""
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(
            buffer, 
            pagesize=letter, 
            leftMargin=36, 
            rightMargin=36, 
            topMargin=36, 
            bottomMargin=36
        )

        styles = getSampleStyleSheet()
        
        # Custom premium style definitions
        title_style = ParagraphStyle(
            name='DocTitle',
            parent=styles['Normal'],
            fontName='Helvetica-Bold',
            fontSize=22,
            leading=26,
            textColor=colors.HexColor('#0f172a'),
            spaceAfter=6
        )
        
        subtitle_style = ParagraphStyle(
            name='DocSubTitle',
            parent=styles['Normal'],
            fontName='Helvetica',
            fontSize=11,
            leading=14,
            textColor=colors.HexColor('#64748b'),
            spaceAfter=20
        )
        
        h1_style = ParagraphStyle(
            name='SectionHeader',
            parent=styles['Normal'],
            fontName='Helvetica-Bold',
            fontSize=14,
            leading=18,
            textColor=colors.HexColor('#0f172a'),
            spaceBefore=15,
            spaceAfter=8,
            keepWithNext=True
        )

        body_style = ParagraphStyle(
            name='ReportBody',
            parent=styles['Normal'],
            fontName='Helvetica',
            fontSize=9.5,
            leading=14,
            textColor=colors.HexColor('#334155'),
            spaceAfter=10
        )
        
        summary_style = ParagraphStyle(
            name='AISummaryText',
            parent=styles['Normal'],
            fontName='Helvetica-Oblique',
            fontSize=9.5,
            leading=15,
            textColor=colors.HexColor('#0f172a'),
            spaceAfter=10
        )

        th_style = ParagraphStyle(
            name='TableHeader',
            parent=styles['Normal'],
            fontName='Helvetica-Bold',
            fontSize=9,
            leading=11,
            textColor=colors.white,
            alignment=0
        )
        
        td_style = ParagraphStyle(
            name='TableCell',
            parent=styles['Normal'],
            fontName='Helvetica',
            fontSize=8.5,
            leading=11,
            textColor=colors.HexColor('#334155'),
            alignment=0
        )

        story = []

        # --- Document Header ---
        story.append(Paragraph("Monthly Purchase Intelligence Report", title_style))
        story.append(Paragraph(f"Prepared for {org_name} ({user_name}) | Month: {month_label} | Generated on {datetime.now().strftime('%d %b %Y')}", subtitle_style))
        
        # Horizontal Rule divider
        hr = Table([['']], colWidths=[540], rowHeights=[2])
        hr.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,-1), colors.HexColor('#0284c7')),
            ('BOTTOMPADDING', (0,0), (-1,-1), 0),
            ('TOPPADDING', (0,0), (-1,-1), 0),
        ]))
        story.append(hr)
        story.append(Spacer(1, 15))

        # --- Section 1: Executive AI Summary ---
        story.append(Paragraph("Executive Summary (AI Generated)", h1_style))
        # Format summary box
        summary_p = Paragraph(ai_summary, summary_style)
        summary_box = Table([[summary_p]], colWidths=[540])
        summary_box.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,-1), colors.HexColor('#f8fafc')),
            ('BOX', (0,0), (-1,-1), 1, colors.HexColor('#e2e8f0')),
            ('TOPPADDING', (0,0), (-1,-1), 10),
            ('BOTTOMPADDING', (0,0), (-1,-1), 10),
            ('LEFTPADDING', (0,0), (-1,-1), 12),
            ('RIGHTPADDING', (0,0), (-1,-1), 12),
        ]))
        story.append(summary_box)
        story.append(Spacer(1, 15))

        # --- Section 2: Key Purchasing Metrics ---
        story.append(Paragraph("Key Monthly Metrics", h1_style))
        
        # Compile KPI grid data
        total_spend = analytics_data.get("monthly_spend_total", 0.0)
        total_bills = analytics_data.get("monthly_bills_count", 0)
        avg_bill = total_spend / total_bills if total_bills > 0 else 0.0
        unique_dealers = analytics_data.get("monthly_dealers_count", 0)

        kpi_data = [
            [
                Paragraph("<b>Total Spent</b>", td_style), 
                Paragraph("<b>Bills Processed</b>", td_style),
                Paragraph("<b>Avg Bill Amount</b>", td_style), 
                Paragraph("<b>Active Suppliers</b>", td_style)
            ],
            [
                Paragraph(f"₹{total_spend:,.2f}", ParagraphStyle('Kpi1', parent=td_style, fontName='Helvetica-Bold', fontSize=12, textColor=colors.HexColor('#0f172a'))),
                Paragraph(f"{total_bills}", ParagraphStyle('Kpi2', parent=td_style, fontName='Helvetica-Bold', fontSize=12, textColor=colors.HexColor('#0f172a'))),
                Paragraph(f"₹{avg_bill:,.2f}", ParagraphStyle('Kpi3', parent=td_style, fontName='Helvetica-Bold', fontSize=12, textColor=colors.HexColor('#0f172a'))),
                Paragraph(f"{unique_dealers}", ParagraphStyle('Kpi4', parent=td_style, fontName='Helvetica-Bold', fontSize=12, textColor=colors.HexColor('#0f172a'))),
            ]
        ]
        
        kpi_table = Table(kpi_data, colWidths=[135, 135, 135, 135])
        kpi_table.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,-1), colors.HexColor('#f1f5f9')),
            ('ALIGN', (0,0), (-1,-1), 'CENTER'),
            ('BOX', (0,0), (-1,-1), 0.5, colors.HexColor('#cbd5e1')),
            ('INNERGRID', (0,0), (-1,-1), 0.5, colors.HexColor('#cbd5e1')),
            ('TOPPADDING', (0,0), (-1,-1), 8),
            ('BOTTOMPADDING', (0,0), (-1,-1), 8),
        ]))
        story.append(kpi_table)
        story.append(Spacer(1, 15))

        # --- Section 3: Charts Side-by-Side ---
        charts_list = []
        
        cat_chart_bytes = self._generate_category_chart(analytics_data.get("category_spending", []))
        if cat_chart_bytes:
            cat_img = Image(io.BytesIO(cat_chart_bytes), width=260, height=150)
            charts_list.append(cat_img)
            
        trend_chart_bytes = self._generate_monthly_trend_chart(analytics_data.get("monthly_spend_history", []))
        if trend_chart_bytes:
            trend_img = Image(io.BytesIO(trend_chart_bytes), width=260, height=150)
            charts_list.append(trend_img)

        if len(charts_list) == 2:
            charts_table = Table([[charts_list[0], charts_list[1]]], colWidths=[270, 270])
            charts_table.setStyle(TableStyle([
                ('ALIGN', (0,0), (-1,-1), 'CENTER'),
                ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
                ('BOTTOMPADDING', (0,0), (-1,-1), 0),
                ('TOPPADDING', (0,0), (-1,-1), 0),
            ]))
            story.append(KeepTogether(charts_table))
        elif len(charts_list) == 1:
            story.append(KeepTogether(charts_list[0]))
            
        story.append(Spacer(1, 15))

        # --- Section 4: Spending by Category, Supplier, & Products (Keep Together) ---
        table_story = []
        table_story.append(Paragraph("Category Spending Details", h1_style))
        
        cat_spending = analytics_data.get("category_spending", [])
        if cat_spending:
            cat_table_data = [[
                Paragraph("Category", th_style), 
                Paragraph("Total Spent (Incl. Tax)", th_style), 
                Paragraph("Quantity Purchased", th_style)
            ]]
            # Sort categories
            sorted_cats = sorted(cat_spending, key=lambda x: x.get("total_spending", 0), reverse=True)[:5]
            for c in sorted_cats:
                cat_table_data.append([
                    Paragraph(str(c.get("_id", "Uncategorized")), td_style),
                    Paragraph(f"₹{c.get('total_spending', 0.0):,.2f}", td_style),
                    Paragraph(f"{c.get('total_quantity', 0.0):,}", td_style),
                ])
                
            cat_table = Table(cat_table_data, colWidths=[200, 170, 170])
            cat_table.setStyle(TableStyle([
                ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#0f172a')),
                ('BOTTOMPADDING', (0,0), (-1,-1), 6),
                ('TOPPADDING', (0,0), (-1,-1), 6),
                ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, colors.HexColor('#f8fafc')]),
                ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#cbd5e1')),
            ]))
            table_story.append(cat_table)
        else:
            table_story.append(Paragraph("No category spending data available for this month.", body_style))

        # Add Supplier Spending table
        table_story.append(Spacer(1, 10))
        table_story.append(Paragraph("Supplier Spending Summary", h1_style))
        
        dealer_spending = analytics_data.get("dealer_spending", [])
        if dealer_spending:
            dealer_table_data = [[
                Paragraph("Supplier / Dealer", th_style), 
                Paragraph("Total Spent (Incl. Tax)", th_style), 
                Paragraph("Invoice / Bill Count", th_style)
            ]]
            for d in dealer_spending[:5]:
                dealer_table_data.append([
                    Paragraph(str(d.get("_id", "Unknown")), td_style),
                    Paragraph(f"₹{d.get('total_spend', 0.0):,.2f}", td_style),
                    Paragraph(f"{d.get('bill_count', 0)}", td_style)
                ])
            dealer_table = Table(dealer_table_data, colWidths=[220, 160, 160])
            dealer_table.setStyle(TableStyle([
                ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#0f172a')),
                ('BOTTOMPADDING', (0,0), (-1,-1), 6),
                ('TOPPADDING', (0,0), (-1,-1), 6),
                ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, colors.HexColor('#f8fafc')]),
                ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#cbd5e1')),
            ]))
            table_story.append(dealer_table)
        else:
            table_story.append(Paragraph("No supplier spending data available for this month.", body_style))

        # Add top products table
        table_story.append(Spacer(1, 10))
        table_story.append(Paragraph("Top Products Purchased This Month", h1_style))
        
        top_products = analytics_data.get("top_products", [])
        if top_products:
            prod_table_data = [[
                Paragraph("Product Name", th_style), 
                Paragraph("Dealers Used", th_style), 
                Paragraph("Total Qty", th_style),
                Paragraph("Amount Spent (Incl. Tax)", th_style)
            ]]
            for p in top_products[:5]:
                dealers_str = ", ".join(p.get("dealers", []))
                prod_table_data.append([
                    Paragraph(str(p.get("product_name", p.get("_id", "Unknown"))), td_style),
                    Paragraph(dealers_str, td_style),
                    Paragraph(f"{p.get('total_quantity_purchased', 0.0):,}", td_style),
                    Paragraph(f"₹{p.get('total_amount_spent', 0.0):,.2f}", td_style)
                ])
            prod_table = Table(prod_table_data, colWidths=[160, 160, 100, 120])
            prod_table.setStyle(TableStyle([
                ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#0f172a')),
                ('BOTTOMPADDING', (0,0), (-1,-1), 6),
                ('TOPPADDING', (0,0), (-1,-1), 6),
                ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, colors.HexColor('#f8fafc')]),
                ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#cbd5e1')),
            ]))
            table_story.append(prod_table)
        else:
            table_story.append(Paragraph("No product purchase data available for this month.", body_style))
            
        story.append(KeepTogether(table_story))

        # Build document
        doc.build(story)
        buffer.seek(0)
        return buffer.getvalue()

    def _generate_quarterly_category_chart(self, quarterly_category_spending: List[Dict[str, Any]]) -> bytes:
        """Generates a quarterly category stacked bar chart and returns it as png bytes."""
        if not quarterly_category_spending:
            return None

        # Quarters list
        quarters = ["Q1", "Q2", "Q3", "Q4"]
        
        # Summarize categories across the whole year to find top categories
        cat_totals = {}
        for item in quarterly_category_spending:
            cat = item["_id"].get("category", "Uncategorized")
            spent = item.get("total_spending", 0.0)
            cat_totals[cat] = cat_totals.get(cat, 0.0) + spent

        # Sort categories by total spent descending and pick top 4
        top_categories = sorted(cat_totals.items(), key=lambda x: x[1], reverse=True)[:4]
        top_cat_names = [name for name, _ in top_categories]

        # Data structure: category -> list of 4 values (for Q1, Q2, Q3, Q4)
        chart_data = {cat: [0.0, 0.0, 0.0, 0.0] for cat in top_cat_names}
        chart_data["Others"] = [0.0, 0.0, 0.0, 0.0]

        # Populate values
        q_map = {"Q1": 0, "Q2": 1, "Q3": 2, "Q4": 3}
        for item in quarterly_category_spending:
            q = item["_id"].get("quarter")
            cat = item["_id"].get("category", "Uncategorized")
            spent = item.get("total_spending", 0.0)
            
            if q in q_map:
                idx = q_map[q]
                if cat in top_cat_names:
                    chart_data[cat][idx] += spent
                else:
                    chart_data["Others"][idx] += spent

        # Filter out "Others" if it contains no spend at all
        if sum(chart_data["Others"]) == 0:
            del chart_data["Others"]

        # Plotting
        fig, ax = plt.subplots(figsize=(5.5, 3.2))
        
        # Colors: Slate, Sky Blue, Teal, Indigo, Amber, Light Slate
        color_palette = ["#0f172a", "#0284c7", "#0d9488", "#4f46e5", "#d97706", "#64748b"]
        
        bottom = [0.0, 0.0, 0.0, 0.0]
        for i, (cat, values) in enumerate(chart_data.items()):
            color = color_palette[i % len(color_palette)]
            ax.bar(quarters, values, bottom=bottom, label=cat, color=color, width=0.5)
            for j in range(4):
                bottom[j] += values[j]

        ax.set_title("Quarterly Spending by Category", fontsize=11, fontweight="bold", pad=12)
        ax.set_ylabel("Total Spent (₹)", fontsize=8, fontweight="bold")
        ax.legend(loc="upper left", bbox_to_anchor=(1, 1), fontsize=7.5, frameon=False)
        ax.tick_params(axis='both', labelsize=8)
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)
        ax.grid(axis='y', linestyle='--', alpha=0.7)

        plt.tight_layout()
        buf = io.BytesIO()
        plt.savefig(buf, format='png', dpi=200, bbox_inches='tight')
        plt.close(fig)
        buf.seek(0)
        return buf.getvalue()

    def _generate_yearly_trend_chart(self, monthly_spend_history: List[Dict[str, Any]]) -> bytes:
        """Generates a full-year spend trend line chart and returns it as png bytes."""
        if not monthly_spend_history:
            return None

        labels = [item["label"] for item in monthly_spend_history]
        values = [item["total_amount"] for item in monthly_spend_history]

        if not labels:
            return None

        fig, ax = plt.subplots(figsize=(5.5, 3.2))
        
        ax.plot(labels, values, marker='o', linewidth=2.0, color='#4f46e5', label="Spending")
        ax.fill_between(labels, values, color='#eedffc', alpha=0.3)
        
        ax.set_title("Monthly Spend Trend", fontsize=11, fontweight="bold", pad=12)
        ax.set_ylabel("Total Spent (₹)", fontsize=8, fontweight="bold")
        ax.tick_params(axis='both', labelsize=8)
        
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)
        ax.grid(axis='y', linestyle='--', alpha=0.7)
        
        plt.tight_layout()
        buf = io.BytesIO()
        plt.savefig(buf, format='png', dpi=200)
        plt.close(fig)
        buf.seek(0)
        return buf.getvalue()

    def build_yearly_report_pdf(self, 
                                  user_name: str, 
                                  org_name: str, 
                                  year_label: str, 
                                  analytics_data: Dict[str, Any], 
                                  ai_summary: str) -> bytes:
        """Compiles the yearly intelligence report PDF."""
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(
            buffer, 
            pagesize=letter, 
            leftMargin=36, 
            rightMargin=36, 
            topMargin=36, 
            bottomMargin=36
        )

        styles = getSampleStyleSheet()
        
        # Custom premium style definitions
        title_style = ParagraphStyle(
            name='DocTitleYearly',
            parent=styles['Normal'],
            fontName='Helvetica-Bold',
            fontSize=20,
            leading=24,
            textColor=colors.HexColor('#0f172a'),
            spaceAfter=6
        )
        
        subtitle_style = ParagraphStyle(
            name='DocSubTitleYearly',
            parent=styles['Normal'],
            fontName='Helvetica',
            fontSize=10,
            leading=13,
            textColor=colors.HexColor('#64748b'),
            spaceAfter=15
        )
        
        h1_style = ParagraphStyle(
            name='SectionHeaderYearly',
            parent=styles['Normal'],
            fontName='Helvetica-Bold',
            fontSize=13,
            leading=16,
            textColor=colors.HexColor('#0f172a'),
            spaceBefore=12,
            spaceAfter=6,
            keepWithNext=True
        )

        body_style = ParagraphStyle(
            name='ReportBodyYearly',
            parent=styles['Normal'],
            fontName='Helvetica',
            fontSize=9,
            leading=13,
            textColor=colors.HexColor('#334155'),
            spaceAfter=8
        )
        
        summary_style = ParagraphStyle(
            name='AISummaryTextYearly',
            parent=styles['Normal'],
            fontName='Helvetica-Oblique',
            fontSize=9,
            leading=14,
            textColor=colors.HexColor('#0f172a'),
            spaceAfter=8
        )

        th_style = ParagraphStyle(
            name='TableHeaderYearly',
            parent=styles['Normal'],
            fontName='Helvetica-Bold',
            fontSize=8.5,
            leading=10,
            textColor=colors.white,
            alignment=0
        )
        
        td_style = ParagraphStyle(
            name='TableCellYearly',
            parent=styles['Normal'],
            fontName='Helvetica',
            fontSize=8,
            leading=10,
            textColor=colors.HexColor('#334155'),
            alignment=0
        )

        story = []

        # --- Document Header ---
        story.append(Paragraph("Annual Purchase Intelligence Report", title_style))
        story.append(Paragraph(f"Prepared for {org_name} ({user_name}) | Calendar Year: {year_label} | Generated on {datetime.now().strftime('%d %b %Y')}", subtitle_style))
        
        # Horizontal Rule divider
        hr = Table([['']], colWidths=[540], rowHeights=[2])
        hr.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,-1), colors.HexColor('#4f46e5')),
            ('BOTTOMPADDING', (0,0), (-1,-1), 0),
            ('TOPPADDING', (0,0), (-1,-1), 0),
        ]))
        story.append(hr)
        story.append(Spacer(1, 10))

        # --- Section 1: Executive AI Summary & Predictions ---
        story.append(Paragraph("Executive Summary & Predictions (AI Generated)", h1_style))
        summary_p = Paragraph(ai_summary, summary_style)
        summary_box = Table([[summary_p]], colWidths=[540])
        summary_box.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,-1), colors.HexColor('#f8fafc')),
            ('BOX', (0,0), (-1,-1), 0.5, colors.HexColor('#e2e8f0')),
            ('TOPPADDING', (0,0), (-1,-1), 8),
            ('BOTTOMPADDING', (0,0), (-1,-1), 8),
            ('LEFTPADDING', (0,0), (-1,-1), 10),
            ('RIGHTPADDING', (0,0), (-1,-1), 10),
        ]))
        story.append(summary_box)
        story.append(Spacer(1, 10))

        # --- Section 2: Key Purchasing Metrics & YoY ---
        story.append(Paragraph("Annual Key Performance Indicators", h1_style))
        
        total_spend = analytics_data.get("yearly_spend_total", 0.0)
        total_bills = analytics_data.get("yearly_bills_count", 0)
        avg_monthly = total_spend / 12.0 if total_spend > 0 else 0.0
        unique_dealers = analytics_data.get("yearly_dealers_count", 0)
        unique_products = analytics_data.get("yearly_products_count", 0)

        # YoY status values
        yoy_label = "Prior Spend (YoY)"
        if analytics_data.get("has_prior_year"):
            prior_spend = analytics_data["prior_year_spend_total"]
            growth = analytics_data["spend_growth_pct"]
            growth_str = f"₹{prior_spend:,.2f} ({'+' if growth >= 0 else ''}{growth:.1f}%)"
        else:
            growth_str = "Baseline Year"

        kpi_data = [
            [
                Paragraph("<b>Total Spend</b>", td_style), 
                Paragraph("<b>Total Invoices</b>", td_style),
                Paragraph("<b>Monthly Average</b>", td_style), 
                Paragraph("<b>Active Suppliers</b>", td_style),
                Paragraph("<b>Unique Products</b>", td_style),
                Paragraph(f"<b>{yoy_label}</b>", td_style)
            ],
            [
                Paragraph(f"₹{total_spend:,.2f}", ParagraphStyle('YKpi1', parent=td_style, fontName='Helvetica-Bold', fontSize=9, textColor=colors.HexColor('#0f172a'))),
                Paragraph(f"{total_bills}", ParagraphStyle('YKpi2', parent=td_style, fontName='Helvetica-Bold', fontSize=9, textColor=colors.HexColor('#0f172a'))),
                Paragraph(f"₹{avg_monthly:,.2f}", ParagraphStyle('YKpi3', parent=td_style, fontName='Helvetica-Bold', fontSize=9, textColor=colors.HexColor('#0f172a'))),
                Paragraph(f"{unique_dealers}", ParagraphStyle('YKpi4', parent=td_style, fontName='Helvetica-Bold', fontSize=9, textColor=colors.HexColor('#0f172a'))),
                Paragraph(f"{unique_products}", ParagraphStyle('YKpi5', parent=td_style, fontName='Helvetica-Bold', fontSize=9, textColor=colors.HexColor('#0f172a'))),
                Paragraph(growth_str, ParagraphStyle('YKpi6', parent=td_style, fontName='Helvetica-Bold', fontSize=9, textColor=colors.HexColor('#4f46e5' if analytics_data.get("has_prior_year") else '#64748b'))),
            ]
        ]
        
        kpi_table = Table(kpi_data, colWidths=[90, 80, 95, 85, 90, 100])
        kpi_table.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,-1), colors.HexColor('#f1f5f9')),
            ('ALIGN', (0,0), (-1,-1), 'CENTER'),
            ('BOX', (0,0), (-1,-1), 0.5, colors.HexColor('#cbd5e1')),
            ('INNERGRID', (0,0), (-1,-1), 0.5, colors.HexColor('#cbd5e1')),
            ('TOPPADDING', (0,0), (-1,-1), 6),
            ('BOTTOMPADDING', (0,0), (-1,-1), 6),
        ]))
        story.append(kpi_table)
        story.append(Spacer(1, 10))

        # --- Section 3: Visual Dashboard Charts ---
        charts_list = []
        
        quarter_chart_bytes = self._generate_quarterly_category_chart(analytics_data.get("quarterly_category_spending", []))
        if quarter_chart_bytes:
            q_img = Image(io.BytesIO(quarter_chart_bytes), width=260, height=145)
            charts_list.append(q_img)
            
        trend_chart_bytes = self._generate_yearly_trend_chart(analytics_data.get("monthly_spend_history", []))
        if trend_chart_bytes:
            trend_img = Image(io.BytesIO(trend_chart_bytes), width=260, height=145)
            charts_list.append(trend_img)

        if len(charts_list) == 2:
            charts_table = Table([[charts_list[0], charts_list[1]]], colWidths=[270, 270])
            charts_table.setStyle(TableStyle([
                ('ALIGN', (0,0), (-1,-1), 'CENTER'),
                ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
                ('BOTTOMPADDING', (0,0), (-1,-1), 0),
                ('TOPPADDING', (0,0), (-1,-1), 0),
            ]))
            story.append(KeepTogether(charts_table))
        elif len(charts_list) == 1:
            story.append(KeepTogether(charts_list[0]))
            
        story.append(Spacer(1, 10))

        # Page Break to keep PDF structured and avoid messy mid-table splits
        story.append(PageBreak())

        # --- Section 4: Data Tables (Page 2) ---
        table_story = []
        table_story.append(Paragraph("Category Spending Details", h1_style))
        
        cat_spending = analytics_data.get("category_spending", [])
        if cat_spending:
            cat_table_data = [[
                Paragraph("Category", th_style), 
                Paragraph("Total Spent (Incl. Tax)", th_style), 
                Paragraph("Quantity Purchased", th_style)
            ]]
            for c in cat_spending[:5]:
                cat_table_data.append([
                    Paragraph(str(c.get("_id", "Uncategorized")), td_style),
                    Paragraph(f"₹{c.get('total_spending', 0.0):,.2f}", td_style),
                    Paragraph(f"{c.get('total_quantity', 0.0):,}", td_style),
                ])
            cat_table = Table(cat_table_data, colWidths=[200, 170, 170])
            cat_table.setStyle(TableStyle([
                ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#4f46e5')),
                ('BOTTOMPADDING', (0,0), (-1,-1), 4),
                ('TOPPADDING', (0,0), (-1,-1), 4),
                ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, colors.HexColor('#f8fafc')]),
                ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#cbd5e1')),
            ]))
            table_story.append(cat_table)
        else:
            table_story.append(Paragraph("No category spending data available.", body_style))

        # Add Supplier table
        table_story.append(Spacer(1, 10))
        table_story.append(Paragraph("Top Suppliers by Spend Volume", h1_style))
        
        dealer_spending = analytics_data.get("dealer_spending", [])
        if dealer_spending:
            dealer_table_data = [[
                Paragraph("Supplier / Dealer", th_style), 
                Paragraph("Total Spend (Incl. Tax)", th_style), 
                Paragraph("Invoice Count", th_style)
            ]]
            for d in dealer_spending[:5]:
                dealer_table_data.append([
                    Paragraph(str(d.get("_id", "Unknown")), td_style),
                    Paragraph(f"₹{d.get('total_spend', 0.0):,.2f}", td_style),
                    Paragraph(f"{d.get('bill_count', 0)}", td_style)
                ])
            dealer_table = Table(dealer_table_data, colWidths=[220, 160, 160])
            dealer_table.setStyle(TableStyle([
                ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#4f46e5')),
                ('BOTTOMPADDING', (0,0), (-1,-1), 4),
                ('TOPPADDING', (0,0), (-1,-1), 4),
                ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, colors.HexColor('#f8fafc')]),
                ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#cbd5e1')),
            ]))
            table_story.append(dealer_table)

        # Add Price Intelligence table
        table_story.append(Spacer(1, 10))
        table_story.append(Paragraph("Price Fluctuation Insights (Inflation Analysis)", h1_style))
        
        price_inc = analytics_data.get("price_increases", [])
        price_dec = analytics_data.get("price_decreases", [])
        
        pi_data = [[
            Paragraph("Product Name", th_style), 
            Paragraph("Earliest Price", th_style), 
            Paragraph("Latest Price", th_style),
            Paragraph("Fluctuation %", th_style)
        ]]
        
        # Display top 3 price increases and top 2 price decreases
        display_fluc = price_inc[:3] + price_dec[:2]
        if display_fluc:
            for item in display_fluc:
                change = item.get("price_change_pct", 0.0)
                change_style = ParagraphStyle(
                    'PIChgYearly', parent=td_style, 
                    textColor=colors.HexColor('#b91c1c' if change > 0 else '#15803d'),
                    fontName='Helvetica-Bold'
                )
                pi_data.append([
                    Paragraph(str(item.get("product_name", "Unknown")), td_style),
                    Paragraph(f"₹{item.get('earliest_price', 0.0):,.2f}", td_style),
                    Paragraph(f"₹{item.get('latest_price', 0.0):,.2f}", td_style),
                    Paragraph(f"{'+' if change >= 0 else ''}{change:.1f}%", change_style)
                ])
            pi_table = Table(pi_data, colWidths=[200, 110, 110, 120])
            pi_table.setStyle(TableStyle([
                ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#4f46e5')),
                ('BOTTOMPADDING', (0,0), (-1,-1), 4),
                ('TOPPADDING', (0,0), (-1,-1), 4),
                ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, colors.HexColor('#f8fafc')]),
                ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#cbd5e1')),
            ]))
            table_story.append(pi_table)
        else:
            table_story.append(Paragraph("No price intelligence comparisons recorded.", body_style))
            
        story.append(KeepTogether(table_story))

        # Build document
        doc.build(story)
        buffer.seek(0)
        return buffer.getvalue()

pdf_report_generator = PDFReportGenerator()
