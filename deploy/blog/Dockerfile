# Static host for docs/blog/index.html (see fly.blog.toml, `make fly-deploy-blog`). The make target stages the page and
# docs/STUDY.md into .blog-build/ and builds from there, so nothing else in the repository enters the image.
FROM nginx:alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY index.html STUDY.md /usr/share/nginx/html/
