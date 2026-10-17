package com.spring.service;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.doAnswer;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Date;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.io.TempDir;

import com.spring.dao.PatrolReportDAO;
import com.spring.dao.PdfCacheDAO;
import com.spring.dto.PatrolReportVO;
import com.spring.dto.PdfCacheVO;

class PdfCacheServiceImplTest {

    @TempDir
    Path temporaryDirectory;

    private String originalCacheRoot;

    @BeforeEach
    void rememberCacheRoot() {
        originalCacheRoot = System.getProperty("SSA_CACHE_ROOT");
    }

    @AfterEach
    void restoreCacheRoot() {
        if (originalCacheRoot == null) {
            System.clearProperty("SSA_CACHE_ROOT");
        } else {
            System.setProperty("SSA_CACHE_ROOT", originalCacheRoot);
        }
    }

    @Test
    void defersCacheValidationUntilPdfRequestAndFailsBeforeDatabaseAccess() {
        System.setProperty("SSA_CACHE_ROOT", "relative/uploads");
        PdfCacheDAO cacheDAO = mock(PdfCacheDAO.class);
        PatrolReportDAO reportDAO = mock(PatrolReportDAO.class);
        PdfCacheService service = new PdfCacheServiceImpl(cacheDAO, reportDAO);

        IllegalStateException error = assertThrows(IllegalStateException.class,
                () -> service.getOrCreatePatrolReportPdf(7L, "http://127.0.0.1:80/app"));

        assertTrue(error.getMessage().contains("SSA_CACHE_ROOT"));
        verifyNoInteractions(cacheDAO, reportDAO);
    }

    @Test
    void readsCacheUnderTheConfiguredCacheRootWithoutLaunchingBrowser() throws Exception {
        System.setProperty("SSA_CACHE_ROOT", temporaryDirectory.toString());
        Path directory = Files.createDirectories(temporaryDirectory.resolve("pdf-cache").resolve("v4"));
        Path cachedFile = Files.writeString(directory.resolve("existing.pdf"), "%PDF-1.7");
        PdfCacheDAO cacheDAO = mock(PdfCacheDAO.class);
        PatrolReportDAO reportDAO = mock(PatrolReportDAO.class);
        when(reportDAO.getReportById(7)).thenReturn(sampleReport());
        when(cacheDAO.selectLatestSuccessPdfCache(7L)).thenReturn(PdfCacheVO.builder()
                .pdfCacheId(10L).reportId(7L).generationStatus("SUCCESS")
                .pdfFilePath(cachedFile.toString()).build());

        Path result = new PdfCacheServiceImpl(cacheDAO, reportDAO)
                .getOrCreatePatrolReportPdf(7L, "http://127.0.0.1:80/app");

        assertEquals(cachedFile, result);
        verify(cacheDAO, never()).insertPdfCacheRequest(any());
    }

    @Test
    void returnsExistingSuccessCacheWhenTheCachedFileStillExists() throws Exception {
        PdfCacheDAO cacheDAO = mock(PdfCacheDAO.class);
        PatrolReportDAO reportDAO = mock(PatrolReportDAO.class);
        Path directory = Files.createTempDirectory("pdf-cache-test");
        Path cachedFile = Files.writeString(directory.resolve("existing.pdf"), "%PDF-1.7");
        when(cacheDAO.selectLatestSuccessPdfCache(7L)).thenReturn(PdfCacheVO.builder()
                .pdfCacheId(10L).reportId(7L).generationStatus("SUCCESS")
                .pdfFilePath(cachedFile.toString()).build());
        when(reportDAO.getReportById(7)).thenReturn(sampleReport());

        PdfCacheService service = new PdfCacheServiceImpl(cacheDAO, reportDAO,
                (url, destination) -> { throw new AssertionError("A cache hit must not render another PDF"); },
                directory);

        assertEquals(cachedFile.toAbsolutePath().normalize(), service.getOrCreatePatrolReportPdf(7L, "http://127.0.0.1:80/app"));
        verify(cacheDAO, never()).insertPdfCacheRequest(any());
    }

    @Test
    void createsAndMarksSuccessWhenThereIsNoUsableCache() throws Exception {
        PdfCacheDAO cacheDAO = mock(PdfCacheDAO.class);
        PatrolReportDAO reportDAO = mock(PatrolReportDAO.class);
        Path directory = Files.createTempDirectory("pdf-cache-test");
        when(reportDAO.getReportById(8)).thenReturn(sampleReport());
        when(cacheDAO.selectLatestSuccessPdfCache(8L)).thenReturn(null);
        doAnswer(invocation -> {
            PdfCacheVO request = invocation.getArgument(0);
            request.setPdfCacheId(41L);
            return 1;
        }).when(cacheDAO).insertPdfCacheRequest(any(PdfCacheVO.class));
        when(cacheDAO.updatePdfCacheSuccess(any(PdfCacheVO.class))).thenReturn(1);

        PdfCacheService service = new PdfCacheServiceImpl(cacheDAO, reportDAO,
                (url, destination) -> Files.writeString(destination, "%PDF-1.7"), directory);

        Path generated = service.getOrCreatePatrolReportPdf(8L, "http://127.0.0.1:80/app");

        assertTrue(Files.isRegularFile(generated));
        assertEquals("%PDF-1.7", new String(Files.readAllBytes(generated), 0, 8,
                java.nio.charset.StandardCharsets.ISO_8859_1));
        verify(cacheDAO).updatePdfCacheSuccess(any(PdfCacheVO.class));
    }

    @Test
    void regeneratesWhenSuccessCacheReferencesAMissingFile() throws Exception {
        PdfCacheDAO cacheDAO = mock(PdfCacheDAO.class);
        PatrolReportDAO reportDAO = mock(PatrolReportDAO.class);
        Path directory = Files.createTempDirectory("pdf-cache-test");
        when(reportDAO.getReportById(12)).thenReturn(sampleReport());
        when(cacheDAO.selectLatestSuccessPdfCache(12L)).thenReturn(PdfCacheVO.builder()
                .pdfCacheId(33L).reportId(12L).generationStatus("SUCCESS")
                .pdfFilePath(directory.resolve("deleted.pdf").toString()).build());
        doAnswer(invocation -> {
            invocation.<PdfCacheVO>getArgument(0).setPdfCacheId(44L);
            return 1;
        }).when(cacheDAO).insertPdfCacheRequest(any(PdfCacheVO.class));
        when(cacheDAO.updatePdfCacheSuccess(any(PdfCacheVO.class))).thenReturn(1);

        PdfCacheService service = new PdfCacheServiceImpl(cacheDAO, reportDAO,
                (url, destination) -> Files.writeString(destination, "%PDF-1.7"), directory);

        assertTrue(Files.isRegularFile(service.getOrCreatePatrolReportPdf(12L, "http://127.0.0.1:80/app")));
        verify(cacheDAO).insertPdfCacheRequest(any(PdfCacheVO.class));
    }

    @Test
    void marksRequestAsFailedWhenPdfWritingFails() throws Exception {
        PdfCacheDAO cacheDAO = mock(PdfCacheDAO.class);
        PatrolReportDAO reportDAO = mock(PatrolReportDAO.class);
        Path directory = Files.createTempDirectory("pdf-cache-test");
        when(reportDAO.getReportById(9)).thenReturn(sampleReport());
        doAnswer(invocation -> {
            invocation.<PdfCacheVO>getArgument(0).setPdfCacheId(55L);
            return 1;
        }).when(cacheDAO).insertPdfCacheRequest(any(PdfCacheVO.class));

        PdfCacheService service = new PdfCacheServiceImpl(cacheDAO, reportDAO,
                (url, destination) -> { throw new java.io.IOException("browser unavailable"); }, directory);

        assertThrows(IllegalStateException.class, () -> service.getOrCreatePatrolReportPdf(9L, "http://127.0.0.1:80/app"));
        verify(cacheDAO).updatePdfCacheFail(eq(55L));
    }

    @Test
    void rejectsAnUnknownReportBeforeCreatingACacheRequest() throws Exception {
        PdfCacheDAO cacheDAO = mock(PdfCacheDAO.class);
        PatrolReportDAO reportDAO = mock(PatrolReportDAO.class);
        when(reportDAO.getReportById(99)).thenReturn(null);
        Path directory = Files.createTempDirectory("pdf-cache-test");
        PdfCacheService service = new PdfCacheServiceImpl(cacheDAO, reportDAO,
                (url, destination) -> Files.writeString(destination, "%PDF-1.7"), directory);

        assertThrows(com.spring.exception.PatrolReportNotFoundException.class,
                () -> service.getOrCreatePatrolReportPdf(99L, "http://127.0.0.1:80/app"));
        verify(cacheDAO, never()).insertPdfCacheRequest(any());
    }

    private static PatrolReportVO sampleReport() {
        return PatrolReportVO.builder()
                .reportId(8L)
                .reportDate(new Date())
                .patrolDate(new Date())
                .memberId("admin")
                .totalFlightTime(1.5D)
                .totalDetectCount(3L)
                .completionRate(66.7D)
                .actionTaken("현장 확인 완료")
                .remark("특이사항 없음")
                .build();
    }
}
