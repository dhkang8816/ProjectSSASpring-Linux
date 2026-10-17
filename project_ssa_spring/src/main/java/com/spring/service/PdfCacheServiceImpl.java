package com.spring.service;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.security.SecureRandom;
import java.util.Base64;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.function.Supplier;

import com.spring.dao.PatrolReportDAO;
import com.spring.dao.PdfCacheDAO;
import com.spring.dto.PatrolReportVO;
import com.spring.dto.PdfCacheVO;
import com.spring.exception.InvalidRequestException;
import com.spring.exception.PatrolReportNotFoundException;
import com.spring.util.RuntimeSettings;

import lombok.extern.log4j.Log4j2;

@Log4j2
public class PdfCacheServiceImpl implements PdfCacheService {

    private final PdfCacheDAO pdfCacheDAO;
    private final PatrolReportDAO patrolReportDAO;
    private static final long TOKEN_TTL_MILLIS = 60_000L;
    private final PatrolReportPdfRenderer pdfRenderer;
    private final Supplier<Path> cacheDirectory;
    private final Map<String, Long> renderTokens = new ConcurrentHashMap<>();

    public PdfCacheServiceImpl(PdfCacheDAO pdfCacheDAO, PatrolReportDAO patrolReportDAO) {
        this(pdfCacheDAO, patrolReportDAO, new HeadlessChromePdfRenderer(),
                () -> RuntimeSettings.cacheRoot().resolve("pdf-cache").resolve("v4"));
    }

    PdfCacheServiceImpl(PdfCacheDAO pdfCacheDAO, PatrolReportDAO patrolReportDAO,
            PatrolReportPdfRenderer pdfRenderer, Path cacheDirectory) {
        this(pdfCacheDAO, patrolReportDAO, pdfRenderer, () -> cacheDirectory.toAbsolutePath().normalize());
    }

    private PdfCacheServiceImpl(PdfCacheDAO pdfCacheDAO, PatrolReportDAO patrolReportDAO,
            PatrolReportPdfRenderer pdfRenderer, Supplier<Path> cacheDirectory) {
        this.pdfCacheDAO = pdfCacheDAO;
        this.patrolReportDAO = patrolReportDAO;
        this.pdfRenderer = pdfRenderer;
        this.cacheDirectory = cacheDirectory;
    }

    @Override
    public Path getOrCreatePatrolReportPdf(Long reportId, String renderOrigin) {
        if (reportId == null || reportId <= 0) {
            throw new InvalidRequestException("유효한 업무 보고서 번호가 필요합니다.");
        }
        Path directory = cacheDirectory.get();

        PatrolReportVO report = patrolReportDAO.getReportById(reportId.intValue());
        if (report == null) {
            throw new PatrolReportNotFoundException(reportId);
        }

        PdfCacheVO cached = pdfCacheDAO.selectLatestSuccessPdfCache(reportId);
        Path cachedFile = resolveExistingCacheFile(cached, directory);
        if (cachedFile != null) {
            return cachedFile;
        }

        PdfCacheVO request = PdfCacheVO.builder()
                .reportId(reportId)
                .generationStatus("REQUEST")
                .build();
        if (pdfCacheDAO.insertPdfCacheRequest(request) != 1 || request.getPdfCacheId() == null) {
            throw new IllegalStateException("PDF 캐시 요청을 저장하지 못했습니다.");
        }

        Path destination = directory.resolve("patrol_report_" + reportId + "_" + request.getPdfCacheId() + ".pdf");
        try {
            String token = createRenderToken(reportId);
            try {
                pdfRenderer.render(buildInternalRenderUrl(renderOrigin, reportId, token), destination);
            } finally {
                renderTokens.remove(token);
            }
            if (!Files.isRegularFile(destination) || Files.size(destination) == 0) {
                throw new IOException("PDF output file was not created.");
            }

            request.setPdfFilePath(destination.toString());
            request.setGenerationStatus("SUCCESS");
            if (pdfCacheDAO.updatePdfCacheSuccess(request) != 1) {
                throw new IllegalStateException("PDF 캐시 완료 상태를 저장하지 못했습니다.");
            }
            return destination;
        } catch (Exception ex) {
            markFailed(request.getPdfCacheId(), ex);
            throw new IllegalStateException("PDF 생성 중 오류가 발생했습니다.", ex);
        }
    }

    @Override
    public boolean isValidInternalRenderToken(Long reportId, String token) {
        if (reportId == null || token == null || token.isBlank()) return false;
        Long expiresAt = renderTokens.get(token);
        if (expiresAt == null || expiresAt < System.currentTimeMillis()) {
            renderTokens.remove(token);
            return false;
        }
        return token.endsWith("." + reportId);
    }

    private String createRenderToken(Long reportId) {
        byte[] random = new byte[24];
        new SecureRandom().nextBytes(random);
        String token = Base64.getUrlEncoder().withoutPadding().encodeToString(random) + "." + reportId;
        renderTokens.entrySet().removeIf(entry -> entry.getValue() < System.currentTimeMillis());
        renderTokens.put(token, System.currentTimeMillis() + TOKEN_TTL_MILLIS);
        return token;
    }

    private static String buildInternalRenderUrl(String renderOrigin, Long reportId, String token) {
        if (renderOrigin == null || !renderOrigin.startsWith("http://127.0.0.1:")) {
            throw new IllegalArgumentException("PDF rendering requires a local report view URL.");
        }
        return renderOrigin + "/patrolreport/internal/pdf/" + reportId + "?token=" + token;
    }

    private Path resolveExistingCacheFile(PdfCacheVO cached, Path directory) {
        if (cached == null || cached.getPdfFilePath() == null || cached.getPdfFilePath().trim().isEmpty()) {
            return null;
        }
        try {
            Path file = Paths.get(cached.getPdfFilePath()).toAbsolutePath().normalize();
            return file.startsWith(directory) && Files.isRegularFile(file) ? file : null;
        } catch (RuntimeException ex) {
            log.warn("Ignoring an invalid PDF cache path. pdfCacheId={}", cached.getPdfCacheId());
            return null;
        }
    }

    private void markFailed(Long pdfCacheId, Exception cause) {
        try {
            if (pdfCacheId != null) {
                pdfCacheDAO.updatePdfCacheFail(pdfCacheId);
            }
        } catch (RuntimeException updateFailure) {
            log.error("Could not mark PDF cache generation as failed. pdfCacheId={}", pdfCacheId, updateFailure);
        }
        log.error("Patrol report PDF generation failed. pdfCacheId={}", pdfCacheId, cause);
    }
}
