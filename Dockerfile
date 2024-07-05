FROM python:3.9.19-slim  

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# Set the working directory
WORKDIR /app

# Install Python dependencies
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

# Copy project files to the working directory
COPY . /app/

RUN touch monasef.db
# Expose port 5288
EXPOSE 5288

# Run the application
CMD ["python", "app.py"]
