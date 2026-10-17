package com.spring.controller;

import java.util.List;
import java.util.Map;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.http.ResponseEntity;
import org.springframework.http.CacheControl;
import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.ResponseBody;

import com.spring.dto.DiagnosticResultVO;
import com.spring.service.FlaskRuntimeControlService;
import com.spring.service.SystemDiagnosticsService;

import lombok.RequiredArgsConstructor;

@Controller
@RequestMapping("/admin/diagnostics")
@RequiredArgsConstructor
public class SystemDiagnosticsController {

    private final SystemDiagnosticsService systemDiagnosticsService;

    @Autowired
    private FlaskRuntimeControlService flaskRuntimeControlService;

    @GetMapping
    public String diagnosticsPage() {
        return "admin/diagnostics";
    }

    @GetMapping(value = "/all", produces = "application/json; charset=UTF-8")
    @ResponseBody
    public ResponseEntity<List<DiagnosticResultVO>> diagnoseAll() {
        return ResponseEntity.ok(systemDiagnosticsService.diagnoseAll());
    }

    @GetMapping(value = "/flask", produces = "application/json; charset=UTF-8")
    @ResponseBody
    public ResponseEntity<Map<String, Object>> flaskRuntimeStatus() {
        return ResponseEntity.ok().cacheControl(CacheControl.noStore()).body(flaskRuntimeControlService.status());
    }

    @PostMapping(value = "/flask/start", produces = "application/json; charset=UTF-8")
    @ResponseBody
    public ResponseEntity<Map<String, Object>> startFlaskRuntime() {
        return ResponseEntity.ok(flaskRuntimeControlService.start());
    }

    @PostMapping(value = "/flask/stop", produces = "application/json; charset=UTF-8")
    @ResponseBody
    public ResponseEntity<Map<String, Object>> stopFlaskRuntime() {
        return ResponseEntity.ok(flaskRuntimeControlService.stop());
    }
}
