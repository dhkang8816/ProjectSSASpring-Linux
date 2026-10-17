package com.spring.controller;

import static org.junit.jupiter.api.Assertions.assertArrayEquals;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.junit.jupiter.api.Assumptions.assumeTrue;
import static org.mockito.Mockito.doAnswer;
import static org.mockito.Mockito.doThrow;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Base64;
import java.util.List;
import java.util.Map;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.mock.web.MockMultipartFile;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.test.util.ReflectionTestUtils;
import org.springframework.web.servlet.mvc.support.RedirectAttributesModelMap;

import com.spring.cmd.PageMaker;
import com.spring.dto.AnimalDetailVO;
import com.spring.dto.DangerLogVO;
import com.spring.dto.DetectionLogVO;
import com.spring.dto.MemberVO;
import com.spring.service.AnimalCounterService;
import com.spring.service.AnimalDetailService;
import com.spring.service.CommonCodeService;
import com.spring.service.DangerLogService;
import com.spring.service.DetectionLogService;
import com.spring.service.MemberService;

import jakarta.servlet.ServletContext;

class PhotoStorageControllerTest {

    private static final byte[] MEMBER_DEFAULT = "bundled member default".getBytes(StandardCharsets.UTF_8);
    private static final byte[] ANIMAL_DEFAULT = "bundled animal default".getBytes(StandardCharsets.UTF_8);
    private static final byte[] PNG = Base64.getDecoder().decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+j3ioAAAAASUVORK5CYII=");

    @TempDir
    Path temporaryDirectory;

    private Path uploadRoot;
    private String previousUploadRoot;
    private MockHttpServletRequest request;
    private MemberService memberService;
    private MemberController memberController;

    @BeforeEach
    void configureIsolatedStorageAndServices() {
        previousUploadRoot = System.getProperty("SSA_UPLOAD_ROOT");
        uploadRoot = temporaryDirectory.resolve("uploads");
        System.setProperty("SSA_UPLOAD_ROOT", uploadRoot.toString());

        // A packed WAR may have no real filesystem path for its resources.
        ServletContext servletContext = mock(ServletContext.class);
        when(servletContext.getResourceAsStream("/resources/images/member/noImage.jpg"))
                .thenAnswer(invocation -> new ByteArrayInputStream(MEMBER_DEFAULT));
        when(servletContext.getResourceAsStream("/resources/images/noImage.jpg"))
                .thenAnswer(invocation -> new ByteArrayInputStream(ANIMAL_DEFAULT));
        request = new MockHttpServletRequest(servletContext);

        memberService = mock(MemberService.class);
        memberController = new MemberController();
        ReflectionTestUtils.setField(memberController, "memberService", memberService);
        ReflectionTestUtils.setField(memberController, "commonCodeService", mock(CommonCodeService.class));
        SecurityContextHolder.getContext().setAuthentication(new UsernamePasswordAuthenticationToken(
                "admin01", null, List.of(new SimpleGrantedAuthority("ROLE_ADMIN"))));
    }

    @AfterEach
    void restoreGlobalConfiguration() {
        if (previousUploadRoot == null) {
            System.clearProperty("SSA_UPLOAD_ROOT");
        } else {
            System.setProperty("SSA_UPLOAD_ROOT", previousUploadRoot);
        }
        SecurityContextHolder.clearContext();
    }

    @Test
    void memberRegistrationPreservesOriginalFilenameAndDatabaseValue() throws Exception {
        MemberVO member = MemberVO.builder().memberId("user01").password("password01")
                .name("테스트 직원").department("운영팀").email("user01@example.com").build();
        MockMultipartFile picture = new MockMultipartFile("pictureFile", "직원 사진 01.png", "image/png", PNG);

        String redirect = memberController.regist(member, picture, false, request);

        assertEquals("redirect:/login", redirect);
        assertTrue(member.getPicture().matches("[0-9a-f]{32}\\$\\$직원 사진 01\\.png"));
        assertArrayEquals(PNG, Files.readAllBytes(uploadRoot.resolve("member").resolve(member.getPicture())));
        verify(memberService).regist(member);
    }

    @Test
    void editingMemberWithoutAnUploadKeepsExistingPictureWithoutCreatingDirectories() throws Exception {
        MemberVO oldMember = memberWithPicture("legacy$$기존 사진.JPG");
        MemberVO update = MemberVO.builder().memberId("user01").picture("forged.png").build();
        when(memberService.getRequiredMemberById("user01")).thenReturn(oldMember);
        when(memberService.modifyMember(update)).thenReturn(1);

        String redirect = memberController.modify(update, null, "false", "", "", false, request);

        assertEquals("redirect:/member/detail?memberId=user01", redirect);
        assertEquals(oldMember.getPicture(), update.getPicture());
        assertFalse(Files.exists(uploadRoot));
        verify(memberService).modifyMember(update);
    }

    @Test
    void memberReplacementAndExplicitDeletionAffectOnlyStoredPicture() throws Exception {
        Path memberDirectory = Files.createDirectories(uploadRoot.resolve("member"));
        String oldName = "legacy$$old picture.jpg";
        Path oldPicture = Files.write(memberDirectory.resolve(oldName), new byte[] { 1, 2 });
        Path otherPicture = Files.write(memberDirectory.resolve("another.jpg"), new byte[] { 3, 4 });
        MemberVO oldMember = memberWithPicture(oldName);
        MemberVO replacement = MemberVO.builder().memberId("user01").build();
        when(memberService.getRequiredMemberById("user01")).thenReturn(oldMember);
        when(memberService.modifyMember(replacement)).thenReturn(1);

        memberController.modify(replacement, new MockMultipartFile("pictureFile", "새 사진.png", "image/png", PNG),
                "false", "", "", false, request);

        assertFalse(Files.exists(oldPicture));
        assertArrayEquals(PNG, Files.readAllBytes(memberDirectory.resolve(replacement.getPicture())));
        assertTrue(Files.exists(otherPicture));

        when(memberService.getRequiredMemberById("user01")).thenReturn(memberWithPicture(replacement.getPicture()));
        MemberVO deletion = MemberVO.builder().memberId("user01").build();
        when(memberService.modifyMember(deletion)).thenReturn(1);
        memberController.modify(deletion, null, "true", "", "", false, request);

        assertEquals("noImage.jpg", deletion.getPicture());
        assertFalse(Files.exists(memberDirectory.resolve(replacement.getPicture())));
        assertTrue(Files.exists(otherPicture));
    }

    @Test
    void failedMemberDatabaseUpdateKeepsOldPhotoAndCleansOnlyNewUpload() throws Exception {
        Path memberDirectory = Files.createDirectories(uploadRoot.resolve("member"));
        String oldName = "legacy$$old.jpg";
        byte[] oldBytes = new byte[] { 1, 2, 3 };
        Files.write(memberDirectory.resolve(oldName), oldBytes);
        when(memberService.getRequiredMemberById("user01")).thenReturn(memberWithPicture(oldName));
        MemberVO replacement = MemberVO.builder().memberId("user01").build();
        when(memberService.modifyMember(replacement)).thenReturn(0);

        String redirect = memberController.modify(replacement,
                new MockMultipartFile("pictureFile", "new.png", "image/png", PNG),
                "false", "", "", false, request);

        assertEquals("redirect:/member/modifyForm?memberId=user01&error=true", redirect);
        assertArrayEquals(oldBytes, Files.readAllBytes(memberDirectory.resolve(oldName)));
        try (var entries = Files.list(memberDirectory)) {
            assertEquals(List.of(oldName), entries.map(path -> path.getFileName().toString()).toList());
        }
    }

    @Test
    void traversalAndSymlinkMemberValuesCannotReadOrDeleteExternalFiles() throws Exception {
        Path memberDirectory = Files.createDirectories(uploadRoot.resolve("member"));
        Path external = Files.write(temporaryDirectory.resolve("external.jpg"), new byte[] { 7, 8, 9 });
        String symlinkName = "legacy$$linked.jpg";
        createSymbolicLink(memberDirectory.resolve(symlinkName), external);

        for (String storedName : List.of("../../external.jpg", symlinkName)) {
            when(memberService.getMemberById("user01")).thenReturn(memberWithPicture(storedName));
            assertImage(memberController.getPicture("user01", request), MEMBER_DEFAULT);

            when(memberService.getRequiredMemberById("user01")).thenReturn(memberWithPicture(storedName));
            MemberVO deletion = MemberVO.builder().memberId("user01").build();
            when(memberService.modifyMember(deletion)).thenReturn(1);
            memberController.modify(deletion, null, "true", "", "", false, request);

            assertEquals("noImage.jpg", deletion.getPicture());
            assertArrayEquals(new byte[] { 7, 8, 9 }, Files.readAllBytes(external));
        }
    }

    @Test
    void missingImagesUsePackedWarDefaultsWithoutWritingStorageDirectories() throws Exception {
        when(memberService.getMemberById("user01")).thenReturn(memberWithPicture("missing.jpg"));
        DetectionLogController detection = detectionController(mock(DetectionLogService.class));
        DangerLogController danger = dangerController(mock(DangerLogService.class));

        assertImage(memberController.getPicture("user01", request), MEMBER_DEFAULT);
        assertImage(animalController().getAnimalImage("noImage.jpg", request), ANIMAL_DEFAULT);
        assertImage(detection.getSnapshot(1, request), MEMBER_DEFAULT);
        assertImage(danger.getDangerSnapshot(1, request), MEMBER_DEFAULT);
        assertFalse(Files.exists(uploadRoot));
    }

    @Test
    void memberImageFallsBackToExistingDefaultBeforeBundledDefault() throws Exception {
        byte[] existingDefault = new byte[] { 1, 5, 9 };
        Files.createDirectories(uploadRoot.resolve("member"));
        Files.write(uploadRoot.resolve("member/noImage.jpg"), existingDefault);
        when(memberService.getMemberById("user01")).thenReturn(memberWithPicture("missing.jpg"));

        assertImage(memberController.getPicture("user01", request), existingDefault);
    }

    @Test
    void animalUploadAndReadKeepJsonFilenameAndCacheContracts() throws Exception {
        AnimalDetailController animal = animalController();
        ResponseEntity<Map<String, Object>> uploaded = animal.uploadPicture(
                new MockMultipartFile("pictureFile", "동물 사진.PNG", "image/png", PNG), request);

        assertEquals(200, uploaded.getStatusCode().value());
        assertNotNull(uploaded.getBody());
        assertEquals(Boolean.TRUE, uploaded.getBody().get("success"));
        String filename = (String) uploaded.getBody().get("fileName");
        assertTrue(filename.matches("[0-9a-f]{32}\\.png"));
        assertArrayEquals(PNG, Files.readAllBytes(uploadRoot.resolve("animals").resolve(filename)));

        ResponseEntity<byte[]> image = animal.getAnimalImage(filename, request);
        assertImage(image, PNG);
        assertEquals(MediaType.IMAGE_PNG, image.getHeaders().getContentType());
        assertEquals("no-store", image.getHeaders().getCacheControl());
        assertEquals(400, animal.getAnimalImage("../external.jpg", request).getStatusCode().value());
        assertEquals(400, animal.getAnimalImage("legacy$$animal.jpg", request).getStatusCode().value());
        assertEquals(400, animal.uploadPicture(
                new MockMultipartFile("pictureFile", "bad.txt", "text/plain", new byte[] { 1 }), request)
                .getStatusCode().value());
    }

    @Test
    void animalSymlinkCannotExposeAFileOutsideStorage() throws Exception {
        AnimalDetailController animal = animalController();
        Path external = Files.write(temporaryDirectory.resolve("external.png"), PNG);
        String filename = "0123456789abcdef0123456789abcdef.png";
        Files.createDirectories(uploadRoot.resolve("animals"));
        createSymbolicLink(uploadRoot.resolve("animals").resolve(filename), external);

        assertImage(animal.getAnimalImage(filename, request), ANIMAL_DEFAULT);
        assertArrayEquals(PNG, Files.readAllBytes(external));
    }

    @Test
    void animalFormsWithoutNewPhotoKeepCrudWorkingWithInvalidStorageConfiguration() {
        System.setProperty("SSA_UPLOAD_ROOT", "invalid-relative-upload-root");
        AnimalDetailService service = mock(AnimalDetailService.class);
        AnimalDetailController animal = new AnimalDetailController(service, mock(AnimalCounterService.class),
                mock(CommonCodeService.class));
        AnimalDetailVO registered = AnimalDetailVO.builder().animalId(1).build();

        assertEquals("redirect:/animal/list", animal.register(registered,
                new RedirectAttributesModelMap(), false, request));
        assertEquals("noImage.jpg", registered.getAnimalPicture());
        verify(service).registerAnimal(registered);

        String oldName = "0123456789abcdef0123456789abcdef.jpg";
        when(service.getAnimalById(1)).thenReturn(
                AnimalDetailVO.builder().animalId(1).animalPicture(oldName).build());
        AnimalDetailVO updated = AnimalDetailVO.builder().animalId(1).build();
        assertEquals("redirect:/animal/list", animal.modify(updated, new PageMaker(),
                new RedirectAttributesModelMap(), false, request));
        assertEquals(oldName, updated.getAnimalPicture());
        verify(service).modifyAnimal(updated);
        assertFalse(Files.exists(uploadRoot));
    }

    @Test
    void animalFormsPersistUuidFilenameAndDeleteOldPhotoAfterDatabaseSuccess() throws Exception {
        AnimalDetailService service = mock(AnimalDetailService.class);
        AnimalDetailController animal = new AnimalDetailController(service, mock(AnimalCounterService.class),
                mock(CommonCodeService.class));
        Path directory = Files.createDirectories(uploadRoot.resolve("animals"));
        String oldName = "0123456789abcdef0123456789abcdef.jpg";
        String newName = "abcdef0123456789abcdef0123456789.png";
        Path oldFile = Files.write(directory.resolve(oldName), new byte[] { 1, 2 });
        Path newFile = Files.write(directory.resolve(newName), PNG);
        AnimalDetailVO registered = AnimalDetailVO.builder().animalId(1).animalPicture(oldName).build();

        animal.register(registered, new RedirectAttributesModelMap(), false, request);

        assertEquals(oldName, registered.getAnimalPicture());
        verify(service).registerAnimal(registered);
        when(service.getAnimalById(1)).thenReturn(registered);
        AnimalDetailVO updated = AnimalDetailVO.builder().animalId(1).animalPicture(newName).build();
        doAnswer(invocation -> {
            assertTrue(Files.exists(oldFile), "Old photo must remain until database modification succeeds");
            assertTrue(Files.exists(newFile));
            assertEquals(newName, updated.getAnimalPicture());
            return null;
        }).when(service).modifyAnimal(updated);

        animal.modify(updated, new PageMaker(), new RedirectAttributesModelMap(), false, request);

        assertEquals(newName, updated.getAnimalPicture());
        assertFalse(Files.exists(oldFile));
        assertArrayEquals(PNG, Files.readAllBytes(newFile));
    }

    @Test
    void failedAnimalDatabaseModificationKeepsOldPhotoAndCleansNewUpload() throws Exception {
        AnimalDetailService service = mock(AnimalDetailService.class);
        AnimalDetailController animal = new AnimalDetailController(service, mock(AnimalCounterService.class),
                mock(CommonCodeService.class));
        Path directory = Files.createDirectories(uploadRoot.resolve("animals"));
        String oldName = "0123456789abcdef0123456789abcdef.jpg";
        String newName = "abcdef0123456789abcdef0123456789.png";
        byte[] oldBytes = new byte[] { 1, 2 };
        Path oldFile = Files.write(directory.resolve(oldName), oldBytes);
        Path newFile = Files.write(directory.resolve(newName), PNG);
        when(service.getAnimalById(1)).thenReturn(
                AnimalDetailVO.builder().animalId(1).animalPicture(oldName).build());
        AnimalDetailVO updated = AnimalDetailVO.builder().animalId(1).animalPicture(newName).build();
        doThrow(new IllegalStateException("simulated database failure")).when(service).modifyAnimal(updated);

        assertThrows(IllegalStateException.class, () -> animal.modify(updated, new PageMaker(),
                new RedirectAttributesModelMap(), false, request));

        assertArrayEquals(oldBytes, Files.readAllBytes(oldFile));
        assertFalse(Files.exists(newFile));
    }

    @Test
    void snapshotControllersUseTheirExistingSubdirectoriesUnderTheSameRoot() throws Exception {
        DetectionLogService detectionService = mock(DetectionLogService.class);
        DangerLogService dangerService = mock(DangerLogService.class);
        DetectionLogController detection = detectionController(detectionService);
        DangerLogController danger = dangerController(dangerService);
        byte[] detectedImage = new byte[] { 10, 11 };
        byte[] dangerImage = new byte[] { 20, 21 };
        Files.createDirectories(uploadRoot.resolve("detection"));
        Files.createDirectories(uploadRoot.resolve("dangerlog"));
        Files.write(uploadRoot.resolve("detection/탐지 01.jpg"), detectedImage);
        Files.write(uploadRoot.resolve("dangerlog/danger_01.jpg"), dangerImage);
        when(detectionService.getDetectionLogById(1)).thenReturn(
                DetectionLogVO.builder().dlogId(1).snapshotPath("탐지 01.jpg").build());
        when(dangerService.getDangerLogById(2)).thenReturn(
                DangerLogVO.builder().danlogId(2).dsnapshotPath("danger_01.jpg").build());

        assertImage(detection.getSnapshot(1, request), detectedImage);
        ResponseEntity<byte[]> dangerResponse = danger.getDangerSnapshot(2, request);
        assertImage(dangerResponse, dangerImage);
        assertEquals(MediaType.IMAGE_JPEG, dangerResponse.getHeaders().getContentType());

        when(detectionService.getDetectionLogById(1)).thenReturn(
                DetectionLogVO.builder().snapshotPath("../../external.jpg").build());
        when(dangerService.getDangerLogById(2)).thenReturn(
                DangerLogVO.builder().dsnapshotPath("../../external.jpg").build());
        Files.write(temporaryDirectory.resolve("external.jpg"), new byte[] { 30, 31 });
        assertImage(detection.getSnapshot(1, request), MEMBER_DEFAULT);
        assertImage(danger.getDangerSnapshot(2, request), MEMBER_DEFAULT);
    }

    @Test
    void directoryCreationFailureKeepsMemberRegistrationAndReturnsAnimalUploadError() throws Exception {
        byte[] obstruction = new byte[] { 5, 6 };
        Files.write(uploadRoot, obstruction);
        MemberVO member = MemberVO.builder().memberId("user01").password("password01")
                .name("테스트 직원").department("운영팀").email("user01@example.com").build();

        assertEquals("redirect:/login", memberController.regist(member,
                new MockMultipartFile("pictureFile", "photo.png", "image/png", PNG), false, request));
        assertEquals("noImage.jpg", member.getPicture());
        verify(memberService).regist(member);

        ResponseEntity<Map<String, Object>> response = animalController().uploadPicture(
                new MockMultipartFile("pictureFile", "animal.png", "image/png", PNG), request);
        assertEquals(500, response.getStatusCode().value());
        assertNotNull(response.getBody());
        assertEquals(Boolean.FALSE, response.getBody().get("success"));
        assertArrayEquals(obstruction, Files.readAllBytes(uploadRoot));
    }

    private MemberVO memberWithPicture(String filename) {
        return MemberVO.builder().memberId("user01").picture(filename).build();
    }

    private AnimalDetailController animalController() {
        return new AnimalDetailController(mock(AnimalDetailService.class), mock(AnimalCounterService.class),
                mock(CommonCodeService.class));
    }

    private DetectionLogController detectionController(DetectionLogService service) {
        DetectionLogController controller = new DetectionLogController();
        ReflectionTestUtils.setField(controller, "detectionLogService", service);
        return controller;
    }

    private DangerLogController dangerController(DangerLogService service) {
        DangerLogController controller = new DangerLogController();
        ReflectionTestUtils.setField(controller, "dangerLogService", service);
        return controller;
    }

    private void assertImage(ResponseEntity<byte[]> response, byte[] expected) {
        assertEquals(200, response.getStatusCode().value());
        assertArrayEquals(expected, response.getBody());
    }

    private void createSymbolicLink(Path link, Path target) {
        try {
            Files.createSymbolicLink(link, target);
        } catch (IOException | UnsupportedOperationException | SecurityException exception) {
            assumeTrue(false, () -> "Symbolic links are unavailable on this platform: " + exception.getMessage());
        }
    }
}
