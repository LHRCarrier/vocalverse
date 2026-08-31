# ---- 构建（Maven 3.9 + JDK 21）----
FROM maven:3.9-eclipse-temurin-21 AS build
WORKDIR /build
COPY pom.xml .
RUN mvn -B -ntp dependency:go-offline
COPY src ./src
RUN mvn -B -ntp package -DskipTests

# ---- 运行（JRE 21）----
FROM eclipse-temurin:21-jre
WORKDIR /app
COPY --from=build /build/target/vocalverse-java-api-*.jar app.jar
EXPOSE 8080
ENTRYPOINT ["java", "-Xmx512m", "-jar", "app.jar"]
