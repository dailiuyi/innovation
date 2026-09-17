import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;

/** Process health only; not an end-to-end database/storage readiness guarantee. */
public class Healthcheck {
    public static void main(String[] args) throws Exception {
        var client = HttpClient.newBuilder().connectTimeout(Duration.ofSeconds(3)).build();
        var request = HttpRequest.newBuilder(URI.create("http://127.0.0.1:8080/captchaImage"))
                .timeout(Duration.ofSeconds(5)).GET().build();
        var response = client.send(request, HttpResponse.BodyHandlers.ofString());
        if (response.statusCode() != 200 || !response.body().matches("(?s).*\"code\"\\s*:\\s*200(?:\\s*[,}]).*")) {
            System.exit(1);
        }
    }
}
