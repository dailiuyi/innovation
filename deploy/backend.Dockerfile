FROM maven:3.9.11-eclipse-temurin-21 AS build
WORKDIR /build
COPY backend/ ./backend/
RUN mvn -f backend/pom.xml -B -ntp package
COPY deploy/Healthcheck.java /build/Healthcheck.java
RUN javac -d /build/healthcheck /build/Healthcheck.java

FROM eclipse-temurin:21.0.8_9-jre-jammy
RUN groupadd --gid 10001 app && useradd --uid 10001 --gid app --no-create-home app \
    && mkdir -p /app/.local/logs /data/artifacts /data/framework-uploads \
    && chown -R app:app /app /data
WORKDIR /app
COPY --from=build --chown=app:app /build/backend/ruoyi-admin/target/ruoyi-admin.jar /app/app.jar
COPY --from=build /build/healthcheck/ /opt/healthcheck/
USER 10001:10001
EXPOSE 8080
ENTRYPOINT ["java", "-Duser.timezone=UTC", "-jar", "/app/app.jar"]
