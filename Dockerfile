# Use an official Python 3.9 image as a base
FROM python:3.9-slim

WORKDIR /tmp
COPY requirements.txt /tmp/

# Install the dependencies
RUN pip install --no-cache-dir -r requirements.txt


ARG CUSTOM_UID=1002
ENV CUSTOM_UID=${CUSTOM_UID}

ARG CUSTOM_GID=1002
ENV CUSTOM_GID=${CUSTOM_GID}

ARG CUSTOM_USERNAME="devserver"
ENV CUSTOM_USERNAME=${CUSTOM_USERNAME}

RUN echo $CUSTOM_UID
RUN if [ -z "$(getent group  ${CUSTOM_GID})" ] ; then addgroup --gid ${CUSTOM_GID} ${CUSTOM_USERNAME}; else echo "GID: ${CUSTOM_GID} already exists"; fi
RUN if [ -z "$(getent passwd ${CUSTOM_UID})" ] ; then adduser --uid ${CUSTOM_UID} --gid ${CUSTOM_GID} --disabled-password --gecos '' ${CUSTOM_USERNAME}; else echo "UID: ${CUSTOM_UID} already exists"; fi
RUN adduser ${CUSTOM_USERNAME} sudo
RUN echo '%sudo ALL=(ALL) NOPASSWD:ALL' >> /etc/sudoers


USER ${CUSTOM_USERNAME}

# Set the working directory to /app
WORKDIR /home/${CUSTOM_USERNAME}/app

# Copy the source files file
COPY . .


EXPOSE 8091

# Run the command to start the app when the container starts
CMD ["python3", "server/app.py", "-c", "config/config.yaml"]