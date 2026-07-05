import io
import pandas as pd
from fpdf import FPDF
from abc import ABC, abstractmethod

class Exporter(ABC):
    @abstractmethod
    def export(self, data_string: str) -> io.BytesIO:
        """Takes a markdown string, extracts the table, and returns a binary stream."""
        pass
        
    def extract_table_data(self, data_string: str):
        import re, csv
        
        # Check for CSV code block
        csv_match = re.search(r'```(?:csv|text)\n(.*?)```', data_string, re.DOTALL)
        if csv_match:
            csv_content = csv_match.group(1).strip()
            reader = csv.reader(io.StringIO(csv_content))
            return [row for row in reader if row]
            
        lines = data_string.split('\n')
        table_lines = [line.strip() for line in lines if '|' in line]
        if not table_lines:
            raise ValueError("No tabular or CSV data found in the provided text.")
            
        parsed_data = []
        import re
        
        def clean_markdown(text):
            # Remove bold and italic
            text = re.sub(r'\*\*(.*?)\*\*', r'\1', text)
            text = re.sub(r'\*(.*?)\*', r'\1', text)
            # Replace html line breaks with spaces or newlines (spaces preferred for Excel/PDF simple rendering)
            text = text.replace('<br>', ' ').replace('<br/>', ' ').replace('<br >', ' ')
            return text.strip()

        for line in table_lines:
            # Clean leading/trailing pipes
            clean_line = line
            if clean_line.startswith('|'):
                clean_line = clean_line[1:]
            if clean_line.endswith('|'):
                clean_line = clean_line[:-1]
                
            row = [cell.strip() for cell in clean_line.split('|')]
            
            # Check if this is a separator row (e.g. |---|:---:|)
            if all(all(c in '-: ' for c in cell) for cell in row):
                continue
                
            cleaned_row = [clean_markdown(cell) for cell in row]
            parsed_data.append(cleaned_row)
            
        return parsed_data

class ExcelExporter(Exporter):
    def export(self, data_string: str) -> io.BytesIO:
        parsed_data = self.extract_table_data(data_string)
        if not parsed_data or len(parsed_data) < 2:
            raise ValueError("Insufficient table data.")
            
        df = pd.DataFrame(parsed_data[1:], columns=parsed_data[0])
        
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False)
        output.seek(0)
        return output

class PdfExporter(Exporter):
    def export(self, data_string: str) -> io.BytesIO:
        parsed_data = self.extract_table_data(data_string)
        if not parsed_data or len(parsed_data) < 2:
            raise ValueError("Insufficient table data.")
            
        pdf = FPDF(orientation='L')
        pdf.add_page()
        pdf.set_font("helvetica", size=10)
        
        col_widths = []
        for col_idx in range(len(parsed_data[0])):
            max_len = max(len(str(row[col_idx])) for row in parsed_data)
            # Add padding and constrain max width
            col_widths.append(min(max_len * 2.5 + 5, 80))
            
        line_height = pdf.font_size * 2
        for row_idx, row in enumerate(parsed_data):
            if row_idx == 0:
                pdf.set_font("helvetica", style="B", size=10)
            else:
                pdf.set_font("helvetica", size=10)
                
            for col_idx, cell in enumerate(row):
                # fpdf only supports latin-1, so we must encode/decode to drop unsupported unicode (like emojis/smart quotes)
                safe_text = str(cell).encode('latin-1', 'ignore').decode('latin-1')
                pdf.cell(col_widths[col_idx], line_height, txt=safe_text[:60], border=1)
            pdf.ln(line_height)
            
        pdf_bytes = pdf.output()
        output = io.BytesIO(pdf_bytes)
        output.seek(0)
        return output
