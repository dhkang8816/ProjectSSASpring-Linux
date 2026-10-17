package com.spring.controller;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;

import java.util.List;
import java.util.function.BiConsumer;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.test.util.ReflectionTestUtils;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;
import org.springframework.test.web.servlet.request.MockMvcRequestBuilders;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import org.springframework.web.multipart.MultipartFile;

import com.spring.dto.MemberVO;
import com.spring.exception.CommonExceptionAdvice;
import com.spring.exception.InvalidRequestException;
import com.spring.service.MemberService;

class MemberRegistrationValidationTest {

    private MemberController controller;
    private MemberService memberService;
    private MultipartFile picture;
    private MockHttpServletRequest request;

    @BeforeEach
    void configureController() {
        memberService = mock(MemberService.class);
        picture = mock(MultipartFile.class);
        controller = new MemberController();
        ReflectionTestUtils.setField(controller, "memberService", memberService);
        request = new MockHttpServletRequest();
    }

    @Test
    void missingOrWhitespaceEmailStopsBeforePhotoHandlingAndDatabaseInsert() {
        assertMissingValuesRejected(MemberVO::setEmail, "이메일 주소를 입력해 주세요.");
    }

    @Test
    void missingOrWhitespaceMemberIdStopsBeforePhotoHandlingAndDatabaseInsert() {
        assertMissingValuesRejected(MemberVO::setMemberId, "사번(아이디)을 입력해 주세요.");
    }

    @Test
    void missingOrWhitespacePasswordStopsBeforePhotoHandlingAndDatabaseInsert() {
        assertMissingValuesRejected(MemberVO::setPassword, "비밀번호를 입력해 주세요.");
    }

    @Test
    void missingOrWhitespaceNameStopsBeforePhotoHandlingAndDatabaseInsert() {
        assertMissingValuesRejected(MemberVO::setName, "이름을 입력해 주세요.");
    }

    @Test
    void missingOrWhitespaceDepartmentStopsBeforePhotoHandlingAndDatabaseInsert() {
        assertMissingValuesRejected(MemberVO::setDepartment, "소속 부서를 입력해 주세요.");
    }

    @Test
    void malformedEmailStopsBeforePhotoHandlingAndDatabaseInsert() {
        for (String email : List.of("user.example.com", "user@@example.com", "user @example.com",
                "user@example .com", "user@-example.com", "user@example-.com", "user@example..com")) {
            MemberVO member = validMember();
            member.setEmail(email);

            InvalidRequestException exception = assertThrows(InvalidRequestException.class,
                    () -> controller.regist(member, picture, false, request), email);

            assertEquals("올바른 이메일 주소를 입력해 주세요. (예: example@domain.com)", exception.getMessage());
        }
        verifyNoInteractions(memberService, picture);
    }

    @Test
    void normalFormSubmissionDisplaysMissingEmailMessageAsBadRequest() throws Exception {
        assertFormRejected(" \t ", "이메일 주소를 입력해 주세요.");
    }

    @Test
    void normalFormSubmissionDisplaysMalformedEmailMessageAsBadRequest() throws Exception {
        assertFormRejected("invalid-email", "올바른 이메일 주소를 입력해 주세요. (예: example@domain.com)");
    }

    @Test
    void validRegistrationKeepsLoginRedirectAndDefaultPhoto() throws Exception {
        MemberVO member = validMember();

        assertEquals("redirect:/login", controller.regist(member, null, false, request));

        assertEquals("noImage.jpg", member.getPicture());
        verify(memberService).regist(member);
    }

    @Test
    void validPopupRegistrationKeepsExistingSavedRedirect() throws Exception {
        MemberVO member = validMember();

        assertEquals("redirect:/member/list?popupSaved=true", controller.regist(member, null, true, request));

        verify(memberService).regist(member);
    }

    @Test
    void registrationTrimsOnlyEmailAndPreservesPasswordAndOptionalPhone() throws Exception {
        MemberVO member = validMember();
        member.setEmail(" \t user01@example.com \r\n");
        member.setPassword(" password with spaces ");
        member.setPhone(" 010-1234-5678 ");

        controller.regist(member, null, false, request);

        assertEquals("user01@example.com", member.getEmail());
        assertEquals(" password with spaces ", member.getPassword());
        assertEquals(" 010-1234-5678 ", member.getPhone());
        verify(memberService).regist(member);
    }

    @Test
    void optionalPhoneMayBeOmittedAndStandardEmailVariantsRemainValid() throws Exception {
        for (String email : List.of("first.last+ssa@dept.example-domain.com", "user@localhost")) {
            MemberVO member = validMember();
            member.setEmail(email);
            member.setPhone(null);

            assertEquals("redirect:/login", controller.regist(member, null, false, request));
            assertEquals(email, member.getEmail());
            verify(memberService).regist(member);
        }
    }

    private void assertMissingValuesRejected(BiConsumer<MemberVO, String> setter, String message) {
        for (String value : new String[] { null, "", " \t\r\n " }) {
            MemberVO member = validMember();
            setter.accept(member, value);

            InvalidRequestException exception = assertThrows(InvalidRequestException.class,
                    () -> controller.regist(member, picture, false, request));

            assertEquals(message, exception.getMessage());
        }
        verifyNoInteractions(memberService, picture);
    }

    private void assertFormRejected(String email, String message) throws Exception {
        MockMvc mvc = MockMvcBuilders.standaloneSetup(controller)
                .setControllerAdvice(new CommonExceptionAdvice()).build();

        MvcResult result = mvc.perform(MockMvcRequestBuilders.post("/member/regist")
                .param("memberId", "user01")
                .param("password", "password01")
                .param("name", "테스트 직원")
                .param("department", "운영팀")
                .param("email", email)).andReturn();

        assertEquals(400, result.getResponse().getStatus());
        assertEquals("error/errorCommon", result.getModelAndView().getViewName());
        assertEquals(message, result.getModelAndView().getModel().get("errorMsg"));
        verifyNoInteractions(memberService, picture);
    }

    private MemberVO validMember() {
        return MemberVO.builder().memberId("user01").password("password01")
                .name("테스트 직원").department("운영팀").email("user01@example.com").build();
    }
}
