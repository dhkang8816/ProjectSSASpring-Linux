package com.spring.controller;

import java.io.IOException;
import java.nio.file.Path;
import java.util.List;
import java.util.Map;
import java.util.regex.Pattern;

import jakarta.servlet.http.HttpServletRequest; // Tomcat 10 사양 준수

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.stereotype.Controller;
import org.springframework.ui.Model;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.ResponseBody;
import org.springframework.web.multipart.MultipartFile;

import com.spring.cmd.PageMaker;
import com.spring.dto.CommonCodeVO;
import com.spring.dto.MemberVO;
import com.spring.exception.InvalidRequestException;
import com.spring.security.CustomUser;
import com.spring.service.CommonCodeService;
import com.spring.service.MemberService;
import com.spring.util.MultipartFileUpload; // 유틸리티 연동
import com.spring.util.UploadStorage;

import lombok.extern.log4j.Log4j2;

@Log4j2
@Controller
@RequestMapping("/member")
public class MemberController {

    // Use the same address syntax as the registration form's HTML email input.
    private static final Pattern REGISTRATION_EMAIL_PATTERN = Pattern.compile(
            "[a-zA-Z0-9.!#$%&'*+/=?^_`{|}~-]+@[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?"
            + "(?:\\.[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)*");

    @Autowired
    private MemberService memberService;
    
    @Autowired
    private CommonCodeService commonCodeService;

    private boolean isCurrentAdmin() {
        Authentication authentication = SecurityContextHolder.getContext().getAuthentication();
        return authentication != null && authentication.isAuthenticated()
                && authentication.getAuthorities().stream()
                        .anyMatch(authority -> "ROLE_ADMIN".equals(authority.getAuthority()));
    }

    private String getCurrentMemberId() {
        Authentication authentication = SecurityContextHolder.getContext().getAuthentication();
        if (authentication == null || !authentication.isAuthenticated()
                || "anonymousUser".equals(authentication.getPrincipal())) {
            throw new AccessDeniedException("Authentication is required.");
        }

        Object principal = authentication.getPrincipal();
        if (principal instanceof CustomUser && ((CustomUser) principal).getMember() != null) {
            return ((CustomUser) principal).getMember().getMemberId();
        }
        return authentication.getName();
    }

    private void validateMemberAccess(String memberId) {
        if (!isCurrentAdmin() && !getCurrentMemberId().equals(memberId)) {
            throw new AccessDeniedException("A member may edit only their own profile.");
        }
    }

    private void deleteMemberPicture(String fileName) {
        if (fileName == null || fileName.isEmpty() || "noImage.jpg".equals(fileName)) {
            return;
        }
        try {
            UploadStorage.deleteFile(UploadStorage.directory("member"), fileName);
        } catch (IOException | RuntimeException e) {
            log.warn("회원 사진을 안전하게 삭제하지 못했습니다. 파일명 = {}", fileName, e);
        }
    }

    private void validateRegistration(MemberVO member) {
        requireRegistrationValue(member.getMemberId(), "사번(아이디)을 입력해 주세요.");
        requireRegistrationValue(member.getPassword(), "비밀번호를 입력해 주세요.");
        requireRegistrationValue(member.getName(), "이름을 입력해 주세요.");
        requireRegistrationValue(member.getDepartment(), "소속 부서를 입력해 주세요.");
        requireRegistrationValue(member.getEmail(), "이메일 주소를 입력해 주세요.");

        String email = member.getEmail().strip();
        if (!REGISTRATION_EMAIL_PATTERN.matcher(email).matches()) {
            throw new InvalidRequestException("올바른 이메일 주소를 입력해 주세요. (예: example@domain.com)");
        }
        member.setEmail(email);
    }

    private void requireRegistrationValue(String value, String message) {
        if (value == null || value.isBlank()) {
            throw new InvalidRequestException(message);
        }
    }

    @GetMapping("/registForm")
    public String registForm() {
        return "member/memberRegister"; 
    }

    
    @PostMapping("/regist")
    public String regist(MemberVO member, 
                         @RequestParam(value = "pictureFile", required = false) MultipartFile pictureFile,
                         @RequestParam(value = "popup", defaultValue = "false") boolean popup,
                         HttpServletRequest request) throws Exception {
        validateRegistration(member);
        log.info("회원가입 요청 진입: 사번(아이디) = {}", member.getMemberId());
        
        member.setPicture("noImage.jpg"); 

        if (pictureFile != null && !pictureFile.isEmpty()) {
            try {
                String uploadPath = UploadStorage.directory("member").toString();
                String savedName = MultipartFileUpload.saveFile(uploadPath, pictureFile);
                member.setPicture(savedName);
                log.info("회원가입 프로필 사진 유틸리티 저장 성공: 파일명 = {}", savedName);
            } catch (Exception e) {
                log.warn("회원가입 중 파일 업로드 예외 발생 -> 기본 이미지 배치", e);
            }
        }
        
        try {
            memberService.regist(member);
        } catch (Exception e) {
            deleteMemberPicture(member.getPicture());
            throw e;
        }
        return popup ? "redirect:/member/list?popupSaved=true" : "redirect:/login"; 
    }

    
    @GetMapping("/getPicture")
    @ResponseBody
    public ResponseEntity<byte[]> getPicture(@RequestParam("id") String id, HttpServletRequest request) throws IOException {
        try {
            MemberVO member = memberService.getMemberById(id);
            String picture = member == null ? null : member.getPicture();
            Path directory = null;
            try {
                directory = UploadStorage.directory("member");
            } catch (IOException | RuntimeException e) {
                log.warn("회원 사진 저장 경로에 접근할 수 없어 기본 이미지를 사용합니다.", e);
            }
            return UploadStorage.readImage(directory, picture,
                    request.getServletContext(), "/resources/images/member/noImage.jpg");
        } catch (Exception e) {
            log.error("이미지 스트림 전송 중 시스템 예외 발생: ", e);
            return new ResponseEntity<byte[]>(HttpStatus.NOT_FOUND);
        }
    }
    @GetMapping("/list")
    public String getMemberList(PageMaker pageMaker, Model model) throws Exception {
        int totalCount = memberService.getMemberListCount(pageMaker);
        pageMaker.setTotalCount(totalCount);
        
        List<MemberVO> memberList = memberService.getMemberList(pageMaker);
        model.addAttribute("memberList", memberList);
        model.addAttribute("pageMaker", pageMaker);
        model.addAttribute("statusList", commonCodeService.getCodeListByGroup("ACCOUNT_STATUS"));
        model.addAttribute("roleList", commonCodeService.getCodeListByGroup("USER_ROLE"));
        model.addAttribute("currentMemberId", getCurrentMemberId());
        
        return "member/memberList";
    }
    @GetMapping("/detail")
    public String getMemberDetail(@RequestParam("memberId") String memberId, Model model) throws Exception {
        validateMemberAccess(memberId);
        MemberVO member = memberService.getRequiredMemberById(memberId);
        model.addAttribute("canManageAccount", isCurrentAdmin());
        model.addAttribute("member", member);
        return "member/memberDetail"; 
    }
    @GetMapping("/modifyForm")
    public String modifyForm(@RequestParam("memberId") String memberId, Model model) throws Exception {
        validateMemberAccess(memberId);
        MemberVO member = memberService.getRequiredMemberById(memberId);

        boolean canManageAccount = isCurrentAdmin();
        if (canManageAccount) {
            List<CommonCodeVO> statusList = commonCodeService.getCodeListByGroup("ACCOUNT_STATUS");
            List<CommonCodeVO> roleList = commonCodeService.getCodeListByGroup("USER_ROLE");
            model.addAttribute("statusList", statusList);
            model.addAttribute("roleList", roleList);
        }
        model.addAttribute("canManageAccount", canManageAccount);
        model.addAttribute("member", member);
        
        return "member/memberModify";
    }

    
    @PostMapping("/modify")
    public String modify(MemberVO member,
                         @RequestParam(value = "pictureFile", required = false) MultipartFile pictureFile,
                         @RequestParam(value = "deleteOldPicture", defaultValue = "false") String deleteOldPicture,
                         @RequestParam(value = "newPassword", defaultValue = "") String newPassword,
                         @RequestParam(value = "newPasswordConfirm", defaultValue = "") String newPasswordConfirm,
                         @RequestParam(value = "popup", defaultValue = "false") boolean popup,
                         HttpServletRequest request) throws Exception {
        
        log.info("직원 정보 수정 요청 최종 진입: 사번 = {}, 사진삭제플래그 = {}", member.getMemberId(), deleteOldPicture);
        
        validateMemberAccess(member.getMemberId());
        boolean canManageAccount = isCurrentAdmin();
        MemberVO oldMember = memberService.getRequiredMemberById(member.getMemberId());

        boolean passwordChangeRequested = !newPassword.isEmpty() || !newPasswordConfirm.isEmpty();
        if (passwordChangeRequested && (newPassword.isEmpty() || !newPassword.equals(newPasswordConfirm))) {
            return "redirect:/member/modifyForm?memberId=" + member.getMemberId()
                    + "&passwordError=true" + (popup ? "&popup=true" : "");
        }
        // Do not accept a forged password field from the general member binding.
        // The service encrypts this explicit new-password value only when it is present.
        member.setPassword(passwordChangeRequested ? newPassword : null);

        String oldPictureName = oldMember.getPicture();
        String uploadedPicture = null;
        if ("true".equals(deleteOldPicture)) {
            member.setPicture("noImage.jpg");
        } else if (pictureFile != null && !pictureFile.isEmpty()) {
            try {
                String uploadPath = UploadStorage.directory("member").toString();
                uploadedPicture = MultipartFileUpload.saveFile(uploadPath, pictureFile);
                member.setPicture(uploadedPicture);
                log.info("새로운 프로필 사진 저장 성공: {}", uploadedPicture);
            } catch (Exception e) {
                log.error("수정 중 파일 업로드 실패 예외 발생: ", e);
                member.setPicture(oldPictureName);
            }
        } else {
            member.setPicture(oldPictureName);
            log.info("기존 파일명 유지: {}", oldPictureName);
        }

        // A user-edit request is deliberately sent through a SQL statement that
        // has no STATUS or role columns, even if those values are forged in POST data.
        int result;
        try {
            result = canManageAccount
                    ? memberService.modifyMember(member)
                    : memberService.modifyMemberProfile(member);
        } catch (Exception e) {
            deleteMemberPicture(uploadedPicture);
            throw e;
        }
        if (result > 0) {
            // Keep the previous photo until the database update succeeds.
            if ("true".equals(deleteOldPicture) || uploadedPicture != null) {
                deleteMemberPicture(oldPictureName);
            }
            return popup ? "redirect:/member/list?popupSaved=true"
                    : "redirect:/member/detail?memberId=" + member.getMemberId();
        } else {
            deleteMemberPicture(uploadedPicture);
            return "redirect:/member/modifyForm?memberId=" + member.getMemberId()
                    + "&error=true" + (popup ? "&popup=true" : "");
        }
    }

    @PostMapping("/admin/account")
    @ResponseBody
    public ResponseEntity<Map<String, Object>> updateMemberAccount(
            @RequestParam("memberId") String memberId,
            @RequestParam("status") String status,
            @RequestParam("roleCode") String roleCode) throws Exception {
        if (!isCurrentAdmin()) {
            throw new AccessDeniedException("Administrator permission is required.");
        }

        memberService.updateMemberAccount(memberId, status, roleCode, getCurrentMemberId());
        log.info("Administrator account setting updated. targetMemberId={}", memberId);
        return ResponseEntity.ok(Map.of(
                "success", true,
                "message", "계정 상태와 권한을 저장했습니다. 권한은 대상 사용자의 다음 로그인부터 적용됩니다."));
    }
}
