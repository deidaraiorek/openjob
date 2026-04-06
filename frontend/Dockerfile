FROM node:24-alpine

WORKDIR /app/frontend

COPY frontend/package.json frontend/package-lock.json* ./

RUN npm install

COPY frontend ./

CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0", "--port", "5173"]
