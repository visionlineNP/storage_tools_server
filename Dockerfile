# Use an official Python 3.9 image as a base
FROM python:3.9-slim

WORKDIR /tmp
COPY requirements.txt /tmp/

# Install the dependencies
RUN pip install --no-cache-dir -r requirements.txt



# Set the working directory to /app
WORKDIR /app

# Copy the source files file
COPY . .


EXPOSE 8091

# Run the command to start the app when the container starts
CMD ["gunicorn", "-k", "gthread", "-w", "4", "--threads", "20", "-b", "0.0.0.0:8091", "--timeout", "240", "server.app:app"]
