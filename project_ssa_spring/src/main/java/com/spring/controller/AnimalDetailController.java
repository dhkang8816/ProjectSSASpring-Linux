package com.spring.controller;

import java.io.File;
import java.io.IOException;
import java.nio.file.Path;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.stereotype.Controller;
import org.springframework.ui.Model;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.ResponseBody;
import org.springframework.web.servlet.mvc.support.RedirectAttributes;
import org.springframework.web.multipart.MultipartFile;

import jakarta.servlet.http.HttpServletRequest;

import com.spring.cmd.PageMaker;
import com.spring.dto.AnimalCounterVO;
import com.spring.dto.AnimalDetailVO;
import com.spring.dto.CommonCodeVO;
import com.spring.exception.EmptyMultipartFileException;
import com.spring.service.AnimalCounterService;
import com.spring.service.AnimalDetailService;
import com.spring.service.CommonCodeService;
import com.spring.util.MultipartFileUpload;
import com.spring.util.UploadStorage;

import lombok.AllArgsConstructor;
import lombok.extern.log4j.Log4j2;

@Controller
@RequestMapping("/animal")
@AllArgsConstructor
@Log4j2
public class AnimalDetailController {

    private static final String DEFAULT_IMAGE_NAME = "noImage.jpg";

    private final AnimalDetailService animalDetailService;
    private final AnimalCounterService animalCounterService;
    private final CommonCodeService commonCodeService;
    @GetMapping("/list")
    public String animalList(@ModelAttribute("pageMaker") PageMaker pageMaker, Model model) throws Exception {
        List<AnimalDetailVO> animalList = animalDetailService.getAnimalList(pageMaker);
        PageMaker animalTypePageMaker = new PageMaker();
        animalTypePageMaker.setSearchGrpCode("ANIMAL_TYPE");
        animalTypePageMaker.setSearchUseYn("Y");
        animalTypePageMaker.setPerPageNum(1000);
        List<CommonCodeVO> animalTypeList = commonCodeService.getCommonCodeList(animalTypePageMaker);
        
        model.addAttribute("animalList", animalList);
        model.addAttribute("animalTypeList", animalTypeList);
        model.addAttribute("animalStatusList", getActiveCodes("ANIMAL_STATUS"));
        return "animal/animalList"; // WEB-INF/views/animal/list.jsp 매핑
    }
    @GetMapping("/register")
    public String registerForm(Model model) throws Exception {
        PageMaker pm = new PageMaker();
        pm.setSearchGrpCode("ANIMAL_TYPE");
        pm.setSearchUseYn("Y");
        List<CommonCodeVO> animalTypeList = commonCodeService.getCommonCodeList(pm);
        
        model.addAttribute("animalTypeList", animalTypeList);
        model.addAttribute("animalStatusList", getActiveCodes("ANIMAL_STATUS"));
        return "animal/animalRegister";
    }
    @PostMapping("/register")
    public String register(AnimalDetailVO vo, RedirectAttributes rttr,
            @RequestParam(value = "popup", defaultValue = "false") boolean popup,
            HttpServletRequest request) {
        String uploadedPicture = normalizeUploadedPicture(vo.getAnimalPicture(), request);
        vo.setAnimalPicture(uploadedPicture == null ? DEFAULT_IMAGE_NAME : uploadedPicture);
        try {
            animalDetailService.registerAnimal(vo);
        } catch (RuntimeException e) {
            deleteUploadedAnimalPicture(uploadedPicture, request);
            throw e;
        }
        rttr.addFlashAttribute("msg", "REGISTER_SUCCESS");
        return popup ? "redirect:/animal/list?popupSaved=true" : "redirect:/animal/list";
    }
    @GetMapping("/detail")
    public String animalDetail(@RequestParam("animalId") int animalId, @ModelAttribute("pageMaker") PageMaker pageMaker, Model model) throws Exception {
        AnimalDetailVO vo = animalDetailService.getAnimalById(animalId);
        PageMaker pm = new PageMaker();
        pm.setSearchGrpCode("ANIMAL_TYPE");
        pm.setSearchUseYn("Y");
        List<CommonCodeVO> animalTypeList = commonCodeService.getCommonCodeList(pm);
        
        model.addAttribute("animal", vo);
        model.addAttribute("animalTypeList", animalTypeList);
        model.addAttribute("animalStatusList", getActiveCodes("ANIMAL_STATUS"));
        return "animal/animalDetail";
    }
    @PostMapping("/modify")
    public String modify(AnimalDetailVO vo, PageMaker pageMaker, RedirectAttributes rttr,
            @RequestParam(value = "popup", defaultValue = "false") boolean popup,
            HttpServletRequest request) {
        AnimalDetailVO oldAnimal = animalDetailService.getAnimalById(vo.getAnimalId());
        String oldPicture = oldAnimal == null ? null : oldAnimal.getAnimalPicture();
        String uploadedPicture = normalizeUploadedPicture(vo.getAnimalPicture(), request);

        // A modify form without a new upload must never clear ANIMAL_PICTURE.
        vo.setAnimalPicture(uploadedPicture == null
                ? (oldPicture == null || oldPicture.trim().isEmpty() ? DEFAULT_IMAGE_NAME : oldPicture)
                : uploadedPicture);
        try {
            animalDetailService.modifyAnimal(vo);
        } catch (RuntimeException e) {
            if (uploadedPicture != null && !uploadedPicture.equals(oldPicture)) {
                deleteUploadedAnimalPicture(uploadedPicture, request);
            }
            throw e;
        }

        if (uploadedPicture != null && !uploadedPicture.equals(oldPicture)) {
            deleteUploadedAnimalPicture(oldPicture, request);
        }
        rttr.addAttribute("page", pageMaker.getPage());
        rttr.addAttribute("searchType", pageMaker.getSearchType());
        rttr.addAttribute("keyword", pageMaker.getKeyword());
        rttr.addFlashAttribute("msg", "MODIFY_SUCCESS");
        
        return popup ? "redirect:/animal/list?popupSaved=true" : "redirect:/animal/list";
    }
    @PostMapping("/remove")
    public String remove(@RequestParam("animalId") int animalId, PageMaker pageMaker, RedirectAttributes rttr,
            @RequestParam(value = "popup", defaultValue = "false") boolean popup) {
        animalDetailService.removeAnimal(animalId);
        rttr.addAttribute("page", pageMaker.getPage());
        rttr.addAttribute("searchType", pageMaker.getSearchType());
        rttr.addAttribute("keyword", pageMaker.getKeyword());
        rttr.addFlashAttribute("msg", "REMOVE_SUCCESS");
        
        return popup ? "redirect:/animal/list?popupSaved=true" : "redirect:/animal/list";
    }

    @PostMapping(value = "/uploadPicture", produces = MediaType.APPLICATION_JSON_VALUE)
    @ResponseBody
    public ResponseEntity<Map<String, Object>> uploadPicture(
            @RequestParam("pictureFile") MultipartFile pictureFile,
            HttpServletRequest request) {
        try {
            String fileName = MultipartFileUpload.saveImageFile(getAnimalUploadPath(request), pictureFile);
            Map<String, Object> response = new LinkedHashMap<>();
            response.put("success", true);
            response.put("fileName", fileName);
            return ResponseEntity.ok(response);
        } catch (EmptyMultipartFileException | IllegalArgumentException e) {
            return uploadError(HttpStatus.BAD_REQUEST, e.getMessage());
        } catch (Exception e) {
            log.error("Animal image upload failed", e);
            return uploadError(HttpStatus.INTERNAL_SERVER_ERROR, "이미지 업로드에 실패했습니다. 다시 시도하세요.");
        }
    }

    @GetMapping("/image/{fileName:.+}")
    @ResponseBody
    public ResponseEntity<byte[]> getAnimalImage(@PathVariable String fileName, HttpServletRequest request) {
        if (!isSafeAnimalPictureName(fileName)) {
            return ResponseEntity.badRequest().build();
        }
        try {
            Path uploadDirectory = null;
            try {
                uploadDirectory = UploadStorage.directory("animals");
            } catch (IOException | RuntimeException e) {
                log.warn("Animal directory could not be resolved; serving bundled default image", e);
            }
            ResponseEntity<byte[]> response = UploadStorage.readImage(uploadDirectory, fileName,
                    request.getServletContext(), "/resources/images/noImage.jpg");
            if (!response.getStatusCode().is2xxSuccessful()) {
                return response;
            }
            return ResponseEntity.status(response.getStatusCode())
                    .headers(response.getHeaders())
                    .header(HttpHeaders.CACHE_CONTROL, "no-store")
                    .body(response.getBody());
        } catch (IOException | RuntimeException e) {
            log.warn("Animal image could not be read", e);
            return ResponseEntity.notFound().build();
        }
    }

    @GetMapping("/counterList")
    public String animalCounterList(@ModelAttribute("pageMaker") PageMaker pageMaker, Model model) {
        List<AnimalCounterVO> counterList = animalCounterService.getAnimalCounterList(pageMaker);
        
        model.addAttribute("counterList", counterList);
        return "animal/animalCounterList"; // WEB-INF/views/animal/animalCounterList.jsp 매핑
    }

    private List<CommonCodeVO> getActiveCodes(String groupCode) throws Exception {
        return commonCodeService.getCodeListByGroup(groupCode);
    }

    private ResponseEntity<Map<String, Object>> uploadError(HttpStatus status, String message) {
        Map<String, Object> response = new LinkedHashMap<>();
        response.put("success", false);
        response.put("message", message);
        return ResponseEntity.status(status).body(response);
    }

    private String getAnimalUploadPath(HttpServletRequest request) throws IOException {
        return UploadStorage.directory("animals").toString();
    }

    private String normalizeUploadedPicture(String pictureName, HttpServletRequest request) {
        if (pictureName == null || pictureName.trim().isEmpty()) {
            return null;
        }
        String normalizedName = pictureName.trim();
        File file = getStoredAnimalPicture(normalizedName, request);
        return file != null && file.isFile() && !DEFAULT_IMAGE_NAME.equals(normalizedName) ? normalizedName : null;
    }

    private File getStoredAnimalPicture(String fileName, HttpServletRequest request) {
        if (!isSafeAnimalPictureName(fileName)) {
            return null;
        }
        try {
            return UploadStorage.resolveFile(UploadStorage.directory("animals"), fileName).toFile();
        } catch (IOException | RuntimeException e) {
            log.warn("Animal image path could not be resolved", e);
            return null;
        }
    }

    private boolean isSafeAnimalPictureName(String fileName) {
        return DEFAULT_IMAGE_NAME.equals(fileName)
                || (fileName != null && fileName.matches("(?i)^[0-9a-f]{32}\\.(jpg|jpeg|png)$"));
    }

    private void deleteUploadedAnimalPicture(String fileName, HttpServletRequest request) {
        if (!isSafeAnimalPictureName(fileName) || DEFAULT_IMAGE_NAME.equals(fileName)) {
            return;
        }
        try {
            UploadStorage.deleteFile(UploadStorage.directory("animals"), fileName);
        } catch (IOException | RuntimeException e) {
            log.warn("Unused animal image could not be deleted: {}", fileName, e);
        }
    }

}
