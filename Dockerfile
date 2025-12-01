# Use a lightweight Python version
FROM python:3.11-slim

# Set the working directory in the container
WORKDIR /app

# Copy the requirements file and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of your app's code
COPY . .

# Streamlit runs on port 8501 by default, expose it
EXPOSE 8501

# Command to run the app
CMD ["streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0"]