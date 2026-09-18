package com.ruoyi.ar;

import java.util.List;
import java.util.Map;
import java.util.UUID;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
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
        @NotNull @Min(0) Long bytes, @NotNull @Pattern(regexp="[0-9a-f]{64}") String sha256,
        @Size(max=1024) String relativePath) { }
    public record ReplacementFile(@NotNull UUID requestKey, @NotBlank @Size(max=1024) String relativePath,
        @NotNull @Pattern(regexp="RESOURCE_FILE|CLIENT_LIBRARY") String kind,
        @NotNull @Min(0) Long bytes, @NotNull @Pattern(regexp="[0-9a-f]{64}") String sha256) { }
    public record ReplacementInput(@NotNull UUID requestKey, @NotEmpty @Size(max=1000) List<@Valid ReplacementFile> files) { }
    public record PublishInput(@NotNull @Min(0) Long expectedSceneVersion) { }
    public record ZipInput(@NotNull UUID collectionId, @NotNull @Min(1) Long generation) { }

    @GetMapping("/drafts/config") public Map<String,Object> config() { return service.config(); }
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
    @PostMapping("/drafts/{id}/replacements")
    public Map<String,Object> startReplacement(@PathVariable UUID id,@Valid @RequestBody ReplacementInput input) {
        return service.startReplacement(id,input);
    }
    @GetMapping("/drafts/{id}/replacements/{rid}")
    public Map<String,Object> replacement(@PathVariable UUID id,@PathVariable UUID rid) { return service.replacement(id,rid); }
    @PostMapping("/drafts/{id}/replacements/{rid}/cancel")
    public Map<String,Object> cancelReplacement(@PathVariable UUID id,@PathVariable UUID rid) { return service.cancelReplacement(id,rid); }
    @GetMapping("/drafts/{id}/download-manifest")
    public Map<String,Object> manifest(@PathVariable UUID id,
        @RequestParam(required=false) UUID collectionId, @RequestParam(required=false) Long generation) {
        return service.manifest(id,collectionId,generation);
    }
    @RequestMapping(value="/drafts/{id}/files/{fileId}/content", method={RequestMethod.GET, RequestMethod.HEAD})
    public void downloadFile(@PathVariable UUID id,@PathVariable UUID fileId,
        @RequestParam UUID collectionId,@RequestParam long generation,
        HttpServletRequest request,HttpServletResponse response) throws java.io.IOException {
        service.downloadFile(id,fileId,collectionId,generation,request,response);
    }
    @PostMapping("/drafts/{id}/zip-exports")
    public Map<String,Object> zipExport(@PathVariable UUID id,@Valid @RequestBody ZipInput input) throws java.io.IOException {
        return service.zipExport(id,input.collectionId(),input.generation());
    }
    @RequestMapping(value="/drafts/{id}/zip-exports/{exportId}/content", method={RequestMethod.GET, RequestMethod.HEAD})
    public void downloadZip(@PathVariable UUID id,@PathVariable UUID exportId,
        HttpServletRequest request,HttpServletResponse response) throws java.io.IOException {
        service.downloadZip(id,exportId,request,response);
    }
}
