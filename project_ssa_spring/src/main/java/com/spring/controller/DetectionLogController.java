package com.spring.controller;

import java.io.IOException;
import java.nio.file.Path;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

import org.springframework.beans.factory.annotation.Autowired; // 💡 Member 쪽과 스타일 동기화
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.stereotype.Controller;
import org.springframework.ui.Model;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.ResponseBody;
import org.springframework.web.servlet.mvc.support.RedirectAttributes;

import com.spring.cmd.PageMaker;
import com.spring.dto.CommonCodeVO;
import com.spring.dto.DetectionLogVO;
import com.spring.service.CommonCodeService;
import com.spring.service.DetectionLogService;
import com.spring.util.UploadStorage;

import jakarta.servlet.http.HttpServletRequest; // 💡 Tomcat 10 사양 완벽 준수
import lombok.extern.log4j.Log4j2; // 💡 로그 어노테이션 추가

@Log4j2
@Controller
@RequestMapping("/detection")
public class DetectionLogController {

    @Autowired
    private CommonCodeService commonCodeService;

    @Autowired
    private DetectionLogService detectionLogService; // 💡 깔끔하게 의존성 주입 구조 변경
    @GetMapping("/list")
    public String detectionList(@ModelAttribute("pageMaker") PageMaker pageMaker, Model model) throws Exception {
        List<DetectionLogVO> detectionList = detectionLogService.getDetectionLogList(pageMaker);
        PageMaker animalTypePageMaker = new PageMaker();
        animalTypePageMaker.setSearchGrpCode("ANIMAL_TYPE");
        animalTypePageMaker.setSearchUseYn("Y");
        animalTypePageMaker.setPerPageNum(1000);

        Map<String, String> animalTypeNames = new HashMap<>();
        for (CommonCodeVO code : commonCodeService.getCommonCodeList(animalTypePageMaker)) {
            animalTypeNames.put(code.getCode(), code.getCodeName());
        }

        PageMaker actionStatusPageMaker = new PageMaker();
        actionStatusPageMaker.setSearchGrpCode("ACTION_STATUS");
        actionStatusPageMaker.setSearchUseYn("Y");
        actionStatusPageMaker.setPerPageNum(1000);
        Map<String, String> actionStatusNames = new HashMap<>();
        for (CommonCodeVO code : commonCodeService.getCommonCodeList(actionStatusPageMaker)) {
            actionStatusNames.put(code.getCode(), code.getCodeName());
        }
        
        model.addAttribute("detectionList", detectionList);
        model.addAttribute("animalTypeNames", animalTypeNames);
        model.addAttribute("actionStatusNames", actionStatusNames);
        return "detection/detectionList"; 
    }
    @GetMapping("/detail")
    public String detectionDetail(@RequestParam("dlogId") int dlogId, @ModelAttribute("pageMaker") PageMaker pageMaker, Model model) throws Exception {
        DetectionLogVO vo = detectionLogService.getRequiredDetectionLogById(dlogId);

        PageMaker animalTypePageMaker = new PageMaker();
        animalTypePageMaker.setSearchGrpCode("ANIMAL_TYPE");
        animalTypePageMaker.setSearchUseYn("Y");
        animalTypePageMaker.setPerPageNum(1000);

        Map<String, String> animalTypeNames = new HashMap<>();
        for (CommonCodeVO code : commonCodeService.getCommonCodeList(animalTypePageMaker)) {
            animalTypeNames.put(code.getCode(), code.getCodeName());
        }
        
        model.addAttribute("detection", vo);
        model.addAttribute("animalTypeNames", animalTypeNames);
        model.addAttribute("actionStatusList", commonCodeService.getCodeListByGroup("ACTION_STATUS"));
        return "detection/detectionDetail"; 
    }
    @PostMapping("/modify")
    public String modifyActionStatus(DetectionLogVO dlv, PageMaker pageMaker, RedirectAttributes rttr,
            @RequestParam(value = "popup", defaultValue = "false") boolean popup) {
        detectionLogService.modifyActionStatus(dlv);
        
        rttr.addAttribute("page", pageMaker.getPage());
        rttr.addAttribute("searchType", pageMaker.getSearchType());
        rttr.addAttribute("keyword", pageMaker.getKeyword());
        rttr.addFlashAttribute("msg", "MODIFY_SUCCESS");
        
        return popup ? "redirect:/detection/list?popupSaved=true" : "redirect:/detection/list";
    }

    
    @GetMapping("/getSnapshot")
    @ResponseBody
    public ResponseEntity<byte[]> getSnapshot(@RequestParam("dlogId") int dlogId, HttpServletRequest request) throws IOException {
        try {
            DetectionLogVO vo = detectionLogService.getDetectionLogById(dlogId);
            String fileName = (vo == null || vo.getSnapshotPath() == null || vo.getSnapshotPath().isEmpty())
                    ? "noImage.jpg" : vo.getSnapshotPath();
            Path uploadDirectory = null;
            try {
                uploadDirectory = UploadStorage.directory("detection");
            } catch (IOException | RuntimeException e) {
                log.warn("Detection snapshot directory could not be resolved; serving bundled default image", e);
            }
            return UploadStorage.readImage(uploadDirectory, fileName,
                    request.getServletContext(), "/resources/images/member/noImage.jpg");
        } catch (Exception e) {
            log.error("스냅샷 이미지 스트림 전송 중 예외 발생: ", e);
            return new ResponseEntity<byte[]>(HttpStatus.NOT_FOUND);
        }
    }

}
