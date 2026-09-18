package com.ruoyi.ar;

import java.util.Map;
import java.util.UUID;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.validation.Valid;
import jakarta.validation.constraints.*;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/v1")
@Validated
@PreAuthorize("@ss.hasRole('ar_admin')")
@ConditionalOnProperty(name="ar.storage.enabled", havingValue="true")
public class DraftController {
    private final DraftService service;
    public DraftController(DraftService service) { this.service = service; }
    public record DraftInput(@NotNull UUID requestKey, @NotNull @Size(max=2000) String description) { }
    public record EditInput(@NotNull @Size(max=2000) String description, @NotNull @Min(0) Long expectedVersion) { }
    public record FileInput(@NotNull UUID requestKey, @NotBlank @Size(max=255) String fileName,
        @NotNull @Pattern(regexp="RESOURCE_FILE|CLIENT_LIBRARY") String kind,
        @NotNull @Min(0) Long bytes, @NotNull @Pattern(regexp="[0-9a-f]{64}") String sha256) { }
    public record PublishInput(@NotNull @Min(0) Long expectedSceneVersion) { }

    @GetMapping("/drafts/config") public Map<String,Object> config() { return Map.of("maxBytes",service.maxBytes()); }
    @GetMapping("/scenes/{sceneId}/drafts") public Map<String,Object> list(@PathVariable UUID sceneId,
        @RequestParam(defaultValue="20") @Min(1) @Max(100) int limit,
        @RequestParam(defaultValue="0") @Min(0) int offset) { return service.list(sceneId,limit,offset); }
    @PostMapping("/scenes/{sceneId}/drafts")
    public Map<String,Object> create(@PathVariable UUID sceneId,@Valid @RequestBody DraftInput input) { return service.create(sceneId,input); }
    @GetMapping("/drafts/{id}") public Map<String,Object> detail(@PathVariable UUID id) { return service.detail(id); }
    @PutMapping("/drafts/{id}") public Map<String,Object> edit(@PathVariable UUID id,@Valid @RequestBody EditInput input) { return service.edit(id,input); }
    @DeleteMapping("/drafts/{id}")
    @ResponseStatus(org.springframework.http.HttpStatus.NO_CONTENT)
    public void removeDraft(@PathVariable UUID id) { service.removeDraft(id); }
    @PostMapping("/drafts/{id}/publish")
    public Map<String,Object> publish(@PathVariable UUID id,@Valid @RequestBody PublishInput input) {
        return service.publish(id,input.expectedSceneVersion());
    }
    @GetMapping("/drafts/{id}/files") public Map<String,Object> files(@PathVariable UUID id,
        @RequestParam(defaultValue="20") @Min(1) @Max(100) int limit,
        @RequestParam(defaultValue="0") @Min(0) int offset) { return service.files(id,limit,offset); }
    @PostMapping("/drafts/{id}/files") public Map<String,Object> register(@PathVariable UUID id,@Valid @RequestBody FileInput input) { return service.register(id,input); }
    @DeleteMapping("/drafts/{id}/files/{fileId}")
    @ResponseStatus(org.springframework.http.HttpStatus.NO_CONTENT)
    public void remove(@PathVariable UUID id,@PathVariable UUID fileId) { service.remove(id,fileId); }
    @PutMapping(value="/drafts/{id}/files/{fileId}/content",consumes="application/octet-stream")
    public Map<String,Object> upload(@PathVariable UUID id,@PathVariable UUID fileId,HttpServletRequest request) throws java.io.IOException {
        return service.upload(id,fileId,request.getInputStream());
    }
}
