ARG PREVIOUS_FRONTEND_IMAGE=nginx:1.27-alpine
FROM ${PREVIOUS_FRONTEND_IMAGE} AS previous-assets
RUN mkdir -p /usr/share/nginx/html/ext/app/assets

FROM node:20-alpine AS build
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm ci
COPY . .
RUN npm run build

FROM nginx:1.27-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=previous-assets /usr/share/nginx/html/ext/app/assets/ /usr/share/nginx/html/ext/app/assets/
COPY --from=build /app/dist /usr/share/nginx/html/ext/app
COPY manual/ /usr/share/nginx/html/docs/
EXPOSE 80
