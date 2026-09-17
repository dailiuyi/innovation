package com.ruoyi.ar;

import java.math.BigDecimal;
import jakarta.validation.constraints.*;

public record SceneInput(
    @NotBlank @Size(max=200) String name,
    @Size(max=1000) String address,
    @DecimalMin("-180") @DecimalMax("180") BigDecimal longitude,
    @DecimalMin("-90") @DecimalMax("90") BigDecimal latitude,
    String geoCrs,
    @Min(0) Long expectedVersion
) {}
