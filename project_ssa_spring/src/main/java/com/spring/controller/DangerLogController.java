package com.spring.controller;

import java.io.IOException;
import java.nio.file.Path;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

import org.springframework.beans.factory.annotation.Autowired; // 💡 프로젝트 스타일 동기화
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
import com.spring.dto.DangerDetailVO;
import com.spring.dto.DangerLogVO;
import com.spring.service.CommonCodeService;
import com.spring.service.DangerDetailService;
import com.spring.service.DangerLogService;
import com.spring.util.UploadStorage;

import jakarta.servlet.http.HttpServletRequest; // 💡 Tomcat 10 사양 완벽 준수
import lombok.extern.log4j.Log4j2; // 💡 로그 어노테이션 통합 완료

@Log4j2
@Controller
@RequestMapping("/dangerlog")
public class DangerLogController {

    @Autowired
    private DangerLogService dangerLogService;
    
    @Autowired
    private DangerDetailService dangerDetailService;

    @Autowired
    private CommonCodeService commonCodeService;
    @GetMapping("/list")
    public String dangerLogList(@ModelAttribute("pageMaker") PageMaker pageMaker, Model model) throws Exception {
        List<DangerLogVO> dangerLogList = dangerLogService.getDangerLogList(pageMaker);
        PageMaker pm = new PageMaker();
        pm.setPerPageNum(1000);
        List<DangerDetailVO> dangerMasterList = dangerDetailService.getDangerList(pm);
        Map<Integer, String> dangerCodeMap = new HashMap<>();
        for (DangerDetailVO master : dangerMasterList) {
            dangerCodeMap.put(master.getDangerId(), master.getDangerName());
        }
        for (DangerLogVO log : dangerLogList) {
            String matchedName = dangerCodeMap.get(log.getDangerType());
            
            if (matchedName == null) {
                log.setDangerName("미등록객체(" +  log.getDangerType() + ")");
            } else {
                log.setDangerName(matchedName);
            }
        }

        PageMaker actionStatusPageMaker = new PageMaker();
        actionStatusPageMaker.setSearchGrpCode("ACTION_STATUS");
        actionStatusPageMaker.setSearchUseYn("Y");
        actionStatusPageMaker.setPerPageNum(1000);
        Map<String, String> actionStatusNames = new HashMap<>();
        for (CommonCodeVO code : commonCodeService.getCommonCodeList(actionStatusPageMaker)) {
            actionStatusNames.put(code.getCode(), code.getCodeName());
        }
        
        model.addAttribute("dangerLogList", dangerLogList);
        model.addAttribute("actionStatusNames", actionStatusNames);
        return "dangerlog/dangerLogList"; 
    }
    @GetMapping("/detail")
    public String dangerLogDetail(@RequestParam("danlogId") int danlogId, @ModelAttribute("pageMaker") PageMaker pageMaker, Model model) throws Exception {
        DangerLogVO log = dangerLogService.getDangerLogById(danlogId);
        PageMaker pm = new PageMaker();
        pm.setPerPageNum(1000);
        List<DangerDetailVO> dangerMasterList = dangerDetailService.getDangerList(pm);
        
        Map<Integer, String> dangerCodeMap = new HashMap<>();
        for (DangerDetailVO master : dangerMasterList) {
            dangerCodeMap.put(master.getDangerId(), master.getDangerName());
        }
        String matchedName = dangerCodeMap.get(log.getDangerType());
        if (matchedName == null) {
            log.setDangerName("미등록객체(" + log.getDangerType() + ")");
        } else {
            log.setDangerName(matchedName);
        }
        
        model.addAttribute("dangerLog", log);
        model.addAttribute("actionStatusList", commonCodeService.getCodeListByGroup("ACTION_STATUS"));
        return "dangerlog/dangerLogDetail";
    }
    @PostMapping("/modify")
    public String modifyDactionStatus(DangerLogVO dlv, PageMaker pageMaker, RedirectAttributes rttr,
            @RequestParam(value = "popup", defaultValue = "false") boolean popup) {
        dangerLogService.modifyDactionStatus(dlv);
        
        rttr.addAttribute("page", pageMaker.getPage());
        rttr.addAttribute("searchType", pageMaker.getSearchType());
        rttr.addAttribute("keyword", pageMaker.getKeyword());
        rttr.addFlashAttribute("msg", "MODIFY_SUCCESS");
        
        return popup ? "redirect:/dangerlog/list?popupSaved=true" : "redirect:/dangerlog/list";
    }

    
    @GetMapping("/getDangerSnapshot")
    @ResponseBody
    public ResponseEntity<byte[]> getDangerSnapshot(@RequestParam("danlogId") int danlogId, HttpServletRequest request) throws IOException {
        try {
            DangerLogVO vo = dangerLogService.getDangerLogById(danlogId);
            String fileName = (vo == null || vo.getDsnapshotPath() == null || vo.getDsnapshotPath().isEmpty())
                    ? "noImage.jpg" : vo.getDsnapshotPath();
            Path uploadDirectory = null;
            try {
                uploadDirectory = UploadStorage.directory("dangerlog");
            } catch (IOException | RuntimeException e) {
                log.warn("Danger snapshot directory could not be resolved; serving bundled default image", e);
            }
            return UploadStorage.readImage(uploadDirectory, fileName,
                    request.getServletContext(), "/resources/images/member/noImage.jpg");
        } catch (Exception e) {
            log.error("이상객체 스냅샷 이미지 스트림 전송 중 예외 발생: ", e);
            return new ResponseEntity<byte[]>(HttpStatus.NOT_FOUND);
        }
    }

}
