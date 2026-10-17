<%@ page language="java" contentType="text/html; charset=UTF-8"
	pageEncoding="UTF-8"%>
<%@ taglib prefix="c" uri="jakarta.tags.core"%>
<%@ taglib prefix="fmt" uri="jakarta.tags.fmt"%>
<%@ taglib prefix="form" uri="http://www.springframework.org/tags/form"%>

<script>
    (function () {
        const faviconUrl = '<c:url value="/resources/images/KakaoTalk_20260923_120441893.png?v=2"/>';
        let favicon = document.querySelector('link[rel~="icon"]');

        if (!favicon) {
            favicon = document.createElement('link');
            favicon.rel = 'icon';
            favicon.type = 'image/png';
            document.head.appendChild(favicon);
        }

        favicon.href = faviconUrl;
    })();
</script>
<link rel="stylesheet"
	href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.2/css/all.min.css">
<link rel="stylesheet"
	href="${pageContext.request.contextPath}/resources/css/style.css?v=20260921">
<style>

#ssaHeader {
    background-color: #111827 !important; 
    border-bottom: 1px solid #1e293b;
    padding: 0 30px;
    display: flex;
    justify-content: space-between;
    align-items: center;
    box-shadow: 0 4px 20px rgba(0, 0, 0, 0.3);
    box-sizing: border-box;
    font-family: 'Segoe UI', Roboto, 'Malgun Gothic', sans-serif;
}


.system-title {
    margin: 0;
    font-size: 20px;
    font-weight: 800;
    letter-spacing: -0.03em;
}

.system-title a {
    color: #38bdf8 !important; 
    text-decoration: none !important;
    transition: color 0.2s ease;
}

.system-title a:hover {
    color: #0ea5e9 !important;
}


.user-info-box {
    display: flex !important;
    align-items: center !important; 
    gap: 16px;
    height: 100%; 
}

.user-info-box form {
    display: flex !important;
    align-items: center !important; 
    margin: 0 !important;
    padding: 0 !important;
}


.header-profile-link {
    display: inline-block;
    transition: transform 0.2s cubic-bezier(0.34, 1.56, 0.64, 1);
}
.header-profile-link:hover {
    transform: scale(1.1);
}
.header-profile-img {
    width: 34px;
    height: 34px;
    border-radius: 50%;
    object-fit: cover;
    border: 2px solid #334155;
    cursor: pointer;
}


.user-text-info {
    color: #94a3b8;
    font-size: 13px;
    font-weight: 500;
}
.user-text-info strong {
    color: #ffffff;
    font-weight: 600;
    background: rgba(56, 189, 248, 0.1);
    padding: 2px 6px;
    border-radius: 4px;
    margin-right: 2px;
}


.logout-btn-submit {
    background: none !important;
    border: none !important;
    color: #ef4444 !important; 
    font-weight: 700 !important;
    font-size: 13px !important;
    cursor: pointer !important;
    
    
    padding: 0 !important;
    margin: 0 0 0 12px !important; 
    line-height: 1 !important;     
    vertical-align: middle !important; 
    text-decoration: none !important;
    
    display: inline-block !important;
    transition: color 0.2s;
}

.logout-btn-submit:hover {
    color: #f87171 !important;
    text-decoration: underline !important;
}


.alarm-dropdown {
    display: none;
    position: absolute;
    top: 40px;
    right: -10px;
    width: 340px;
    max-height: 420px;
    background-color: #131926 !important; 
    border: 1px solid #334155 !important;
    box-shadow: 0 10px 30px rgba(0, 0, 0, 0.6) !important;
    border-radius: 12px !important;
    z-index: 99999;
    overflow-y: auto;
}


.alarm-dropdown .pop-header-title {
    padding: 14px 18px;
    border-bottom: 1px solid #232d3f;
    background-color: #171e2e;
    font-weight: 700;
    color: #38bdf8;
    font-size: 14px;
    letter-spacing: -0.01em;
}


.alarm-list-content li {
    padding: 0;
    border-bottom: 1px solid #1e293b !important;
    line-height: 1.5;
    background-color: #131926 !important;
    transition: background 0.2s;
}
.alarm-list-content li:hover {
    background-color: #171e2e !important;
}

.alarm-list-content li a {
    display: block;
    padding: 14px 18px;
    color: #cbd5e1 !important; 
    text-decoration: none;
    cursor: pointer;
}


.alarm-dropdown .pop-footer-box {
    padding: 12px;
    text-align: center;
    border-top: 1px solid #232d3f;
    background-color: #171e2e;
    border-bottom-left-radius: 12px;
    border-bottom-right-radius: 12px;
}
.alarm-dropdown .pop-footer-box a {
    text-decoration: none;
    color: #38bdf8;
    font-size: 12px;
    font-weight: 700;
}
.alarm-dropdown .pop-footer-box a:hover {
    text-decoration: underline;
}
</style>
<header id="ssaHeader" class="top-header">
<h1 class="system-title">
<a href="${pageContext.request.contextPath}/">유기동물 보호소 관제시스템</a>
</h1>


<div id="util-box">
    
    <c:if test="${empty sessionScope.SPRING_SECURITY_CONTEXT}">
        <a href="${pageContext.request.contextPath}/login" class="btn-change text-decoration-none py-1 px-3" style="font-size: 13px;">로그인</a>
    </c:if>
    
    
    <c:if test="${not empty sessionScope.SPRING_SECURITY_CONTEXT}">
        <div class="user-info-box">
            
            
            <a href="${pageContext.request.contextPath}/member/detail?memberId=${sessionScope.SPRING_SECURITY_CONTEXT.authentication.principal}" class="header-profile-link" title="내 정보 보기" data-detail-popup data-popup-name="memberDetail">
                <c:url var="headerProfilePictureUrl" value="/member/getPicture">
                    <c:param name="id" value="${sessionScope.SPRING_SECURITY_CONTEXT.authentication.name}" />
                </c:url>
                <img src="${headerProfilePictureUrl}" class="header-profile-img" alt="프로필"
                     onerror="this.onerror=null;this.src='${pageContext.request.contextPath}/resources/images/member/noImage.jpg';">
            </a>
            
            
            <span class="user-text-info"> 
                <strong>${sessionScope.SPRING_SECURITY_CONTEXT.authentication.principal}</strong>님 로그인 중
            </span>
            
            
            <form:form action="${pageContext.request.contextPath}/logout" method="POST" style="display:inline;">
                <button type="submit" class="logout-btn-submit">로그아웃</button>
            </form:form>
            
            
            <div class="alarm-container" style="position: relative; margin-left: 8px; display: inline-block; vertical-align: middle;">
                
                <i class="fa-solid fa-bell" id="alarmBellIcon" style="font-size: 19px; color: #94a3b8; cursor: pointer; transition: color 0.2s;" onmouseover="this.style.color='#ffffff'" onmouseout="this.style.color='#94a3b8'"></i>
                
                
                <span class="alarm-count-badge" style="position: absolute; top: -6px; right: -7px; background-color: #ef4444; color: white; font-size: 9px; padding: 2px 5px; border-radius: 50%; font-weight: 700; display: none;">0</span>
                
                
                <div class="alarm-dropdown">
                    
                    <div class="pop-header-title">🔔 실시간 시스템 경보 알림</div>
                    
                    
                    <ul class="alarm-list-content" style="list-style: none; padding: 0; margin: 0; font-size: 13px;">
                        <c:if test="${empty headerAlertList}">
                            <li class="empty-alarm-msg text-center text-muted py-4 small" style="background-color: #131926 !important;">새로운 경보 알림이 없습니다.</li>
                        </c:if>
                        <c:if test="${not empty headerAlertList}">
                            <c:forEach var="alert" items="${headerAlertList}">
                                <c:choose>
                                    <c:when test="${not empty alert.dlogId}">
                                        <c:set var="headerAlertUrl" value="${pageContext.request.contextPath}/detection/detail?dlogId=${alert.dlogId}" />
                                        <c:set var="headerAlertPopupName" value="detectionDetail" />
                                    </c:when>
                                    <c:when test="${not empty alert.danlogId}">
                                        <c:set var="headerAlertUrl" value="${pageContext.request.contextPath}/dangerlog/detail?danlogId=${alert.danlogId}" />
                                        <c:set var="headerAlertPopupName" value="dangerLogDetail" />
                                    </c:when>
                                    <c:otherwise>
                                        <c:set var="headerAlertUrl" value="${pageContext.request.contextPath}/alert/alertDetail?alertId=${alert.alertId}" />
                                        <c:set var="headerAlertPopupName" value="alertDetail" />
                                    </c:otherwise>
                                </c:choose>
                                
                                <li>
                                    <a data-detail-popup data-popup-name="${headerAlertPopupName}" href="${headerAlertUrl}">
                                        <span style="display: block; font-weight: 500;"> 
                                            <c:choose>
                                                <c:when test="${alert.alertType eq '1'}">
                                                    <span style="color: #ef4444; font-weight: 700;">[이상객체] </span>
                                                </c:when>
                                                <c:otherwise>
                                                    <span style="color: #f59e0b; font-weight: 700;">[개체미달] </span>
                                                </c:otherwise>
                                            </c:choose> 
                                            <c:out value="${alert.alertMsg}" />
                                        </span> 
                                        <span style="display: block; font-size: 11px; color: #64748b; margin-top: 4px; text-align: right;">
                                            <fmt:formatDate value="${alert.firstSendTime}" pattern="MM-dd HH:mm" />
                                        </span>
                                    </a>
                                </li>
                            </c:forEach>
                        </c:if>
                    </ul>
                    
                    
                    <div class="pop-footer-box">
                        <a href="${pageContext.request.contextPath}/alert/list">전체 이력 보기</a>
                    </div>
                </div> 
            </div> 
            
        </div> 
    </c:if>
</div> 
</header>
<script
	src="${pageContext.request.contextPath}/resources/js/jquery-1.12.3.js"></script>

<script>
$(document).ready(function() {
    if (!document.getElementById('alarmBellIcon')) {
        return;
    }

    $('#alarmBellIcon').on('click', function(e) {
        e.stopPropagation();
        $('.alarm-dropdown').fadeToggle(150);
        $(this).removeClass('fa-shake').css('color', '#ffffff');
    });
    $('.alarm-dropdown').on('click', function(e) {
        var detailLink = e.target.closest('a[data-detail-popup]');
        if (detailLink) {
            e.preventDefault();
            e.stopPropagation();
            openDetailPopup(detailLink.href, detailLink.getAttribute('data-popup-name'));
            return;
        }
        e.stopPropagation();
    });
    $(document).on('click', function() {
        $('.alarm-dropdown').fadeOut(100);
    });
    let lastProcessedAlertId = null;
    const headerContextPath = '${pageContext.request.contextPath}';

    function getAlertDestination(alertData) {
        if (alertData.dlogId) {
            return {
                url: headerContextPath + '/detection/detail?dlogId=' + encodeURIComponent(alertData.dlogId),
                popupName: 'detectionDetail'
            };
        }
        if (alertData.danlogId) {
            return {
                url: headerContextPath + '/dangerlog/detail?danlogId=' + encodeURIComponent(alertData.danlogId),
                popupName: 'dangerLogDetail'
            };
        }
        return {
            url: headerContextPath + '/alert/alertDetail?alertId=' + encodeURIComponent(alertData.alertId),
            popupName: 'alertDetail'
        };
    }

    function formatAlertTime(value) {
        const date = value ? new Date(value) : null;
        if (!date || Number.isNaN(date.getTime())) {
            return '';
        }
        return String(date.getMonth() + 1).padStart(2, '0') + '-'
            + String(date.getDate()).padStart(2, '0') + ' '
            + String(date.getHours()).padStart(2, '0') + ':'
            + String(date.getMinutes()).padStart(2, '0');
    }

    function buildAlarmItem(alertData) {
        const destination = getAlertDestination(alertData);
        const isDanger = String(alertData.alertType) === '1';
        const typeText = isDanger ? '[이상객체]' : '[개체미달]';
        const typeColor = isDanger ? '#ef4444' : '#f59e0b';
        const $link = $('<a>', {
            href: destination.url,
            'data-detail-popup': '',
            'data-popup-name': destination.popupName
        });
        $link.append($('<span>', {
            text: typeText + ' ',
            css: { color: typeColor, fontWeight: '700' }
        }));
        $link.append(document.createTextNode(alertData.alertMsg || '새 경보가 발생했습니다.'));

        const $item = $('<li>');
        $item.append($link);
        const timeText = formatAlertTime(alertData.firstSendTime || alertData.sendDate);
        if (timeText) {
            $item.append($('<span>', {
                text: timeText,
                css: {
                    display: 'block', fontSize: '11px', color: '#64748b',
                    margin: '4px 18px 8px', textAlign: 'right'
                }
            }));
        }
        return $item;
    }

    async function loadRecentAlarms() {
        try {
            const response = await fetch(headerContextPath + '/api/event/recent?t=' + Date.now(), {
                cache: 'no-store'
            });
            if (!response.ok) {
                return;
            }
            const alerts = await response.json();
            if (!Array.isArray(alerts)) {
                return;
            }

            const $list = $('.alarm-list-content').empty();
            if (!alerts.length) {
                $list.append($('<li>', {
                    class: 'empty-alarm-msg text-center text-muted py-4 small',
                    text: '새로운 경보 알림이 없습니다.'
                }));
                return;
            }
            alerts.forEach(function(alertData) {
                $list.append(buildAlarmItem(alertData));
            });
            lastProcessedAlertId = alerts[0].alertId;
        } catch (error) {
            console.error('Header alert bootstrap failed.', error);
        }
    }

    const pollAlertServer = async () => {
        try {
            const response = await fetch('${pageContext.request.contextPath}/api/event/latest?t=' + new Date().getTime());
            
            if (response.ok) {
                const alertData = await response.json();
                
                if (alertData && alertData.alertId !== undefined) {
                    if (lastProcessedAlertId === null) {
                        lastProcessedAlertId = alertData.alertId;
                    } 
                    else if (alertData.alertId !== lastProcessedAlertId) {
                        appendRealtimeAlarm(alertData);
                        $('.alarm-dropdown').fadeIn(200);
                        
                        lastProcessedAlertId = alertData.alertId;
                    }
                }
            }
        } catch (error) {
            console.error(" [알림 레이더 통신 대기] 경보 서버 상태를 확인 중입니다...", error);
        }
        setTimeout(pollAlertServer, 5000);
    };
    function appendRealtimeAlarm(alertData) {
        $('.empty-alarm-msg').remove();
        $('.alarm-list-content').prepend(buildAlarmItem(alertData));
        document.dispatchEvent(new CustomEvent('ssa:alert-received', {
            detail: alertData
        }));
        let $listContainer = $('.alarm-list-content');
        
        while ($listContainer.children('li').length > 5) {
            $listContainer.children('li').last().remove(); // 5개를 초과하는 순간 맨 하단행 영구 소멸
        }
        $('#alarmBellIcon').addClass('fa-shake').css('color', '#ff4d4d');
        let currentCount = parseInt($('.alarm-count-badge').text()) || 0;
        $('.alarm-count-badge').text(currentCount + 1).show();
    }
    <c:if test="${not empty sessionScope.SPRING_SECURITY_CONTEXT}">
        loadRecentAlarms().finally(pollAlertServer);
    </c:if>
});

</script>
<script>
    const POPUP_SIZE = {
        sm: { width: 560, height: 480 },
        md: { width: 860, height: 760 },
        lg: { width: 1200, height: 820 },
        memberProfile: { width: 680, height: 960 },
        droneForm: { width: 640, height: 860 },
        droneDetail: { width: 640, height: 640 },
        alertTemplateSettings: { width: 860, height: 700 }
    };

    const POPUP_PROFILE = {
        dangerRegister: 'sm',
        droneRegister: 'droneForm',
        dangerDetail: 'sm',
        droneDetail: 'droneDetail',
        codeRegister: 'md',
        codeDetail: 'md',
        animalRegister: 'md',
        animalDetail: 'md',
        memberDetail: 'memberProfile',
        memberRegister: 'memberProfile',
        alertDetail: 'md',
        flightHistoryDetail: 'md',
        detectionDetail: 'lg',
        dangerLogDetail: 'lg',
        animalCounterList: 'lg',
        patrolReportDetail: 'lg',
        patrolReportRegister: 'lg',
        workFlowDetail: 'lg',
        alertTemplateSettings: 'alertTemplateSettings'
    };

    function openPopup(url, windowName, sizeKey) {
        var size = POPUP_SIZE[sizeKey] || POPUP_SIZE.md;
        var maxWidth = screen.availWidth - 40;
        var maxHeight = screen.availHeight - 36;
        var popupWidth = Math.max(320, Math.min(size.width, maxWidth));
        var popupHeight = Math.max(420, Math.min(size.height, maxHeight));
        var left = Math.max(0, Math.round((screen.availWidth - popupWidth) / 2));
        var top = Math.max(12, Math.min(24, screen.availHeight - popupHeight - 12));
        var popup = window.open(url, windowName || 'ssaDetailPopup',
            'width=' + popupWidth + ',height=' + popupHeight + ',left=' + left + ',top=' + top
            + ',resizable=yes,scrollbars=yes');

        if (popup) {
            popup.moveTo(left, top);
            popup.resizeTo(popupWidth, popupHeight);
            popup.focus();
            return false;
        }

        window.location.href = url;
        return false;
    }

    function openDetailPopup(url, windowName) {
        return openPopup(url, windowName, POPUP_PROFILE[windowName] || 'md');
    }

    function openFormPopup(url, windowName) {
        var separator = url.indexOf('?') === -1 ? '?' : '&';
        var popupName = windowName || 'ssaFormPopup';
        return openPopup(url + separator + 'popup=true', popupName, POPUP_PROFILE[popupName] || 'md');
    }

    function closePopupAndRefreshParent(fallbackUrl) {
        if (window.opener && !window.opener.closed) {
            try {
                var rootOpener = window.opener;
                while (rootOpener.opener && !rootOpener.opener.closed) {
                    rootOpener = rootOpener.opener;
                }
                rootOpener.location.reload();
            } catch (error) {
            }
            window.close();
            return false;
        }

        if (fallbackUrl) {
            window.location.href = fallbackUrl;
        }
        return false;
    }
    function downloadTableAsCsv(tableSelector, filename) {
        var table = document.querySelector(tableSelector);
        if (!table) {
            window.alert('CSV 다운로드 대상을 찾을 수 없습니다.');
            return;
        }

        var csvRows = Array.prototype.slice.call(table.querySelectorAll('tr'))
            .map(function(row) {
                return Array.prototype.slice.call(row.querySelectorAll('th, td'))
                    .map(function(cell) {
                        var value = (cell.innerText || cell.textContent || '')
                            .replace(/\r?\n|\r/g, ' ')
                            .replace(/\s{2,}/g, ' ')
                            .trim()
                            .replace(/"/g, '""');
                        return '"' + value + '"';
                    }).join(',');
            }).filter(function(row) { return row.length > 0; });

        if (csvRows.length < 2) {
            window.alert('다운로드할 목록 데이터가 없습니다.');
            return;
        }

        var blob = new Blob(['\ufeff' + csvRows.join('\r\n')], { type: 'text/csv;charset=utf-8;' });
        var link = document.createElement('a');
        link.href = URL.createObjectURL(blob);
        link.download = (filename || 'ssa-list') + '-' + new Date().toISOString().slice(0, 10) + '.csv';
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        URL.revokeObjectURL(link.href);
    }

    document.addEventListener('click', function(event) {
        var link = event.target.closest('a[data-detail-popup]');
        if (!link || event.ctrlKey || event.metaKey || event.shiftKey || event.button !== 0) {
            return;
        }
        event.preventDefault();
        openDetailPopup(link.href, link.dataset.popupName);
    });

    (function closeSavedPopup() {
        if (new URLSearchParams(window.location.search).get('popupSaved') !== 'true' || !window.opener) {
            return;
        }

        try {
            var rootOpener = window.opener;
            while (rootOpener.opener && !rootOpener.opener.closed) {
                rootOpener = rootOpener.opener;
            }
            rootOpener.location.reload();
            window.close();
        } catch (error) {
        }
    })();
</script>
