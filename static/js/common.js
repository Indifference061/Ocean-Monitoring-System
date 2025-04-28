$(document).ready(function() {
    // 加载传感器列表
    function loadSensors() {
        $.get("/get_nodes", function(data) {
            $('#sensor-list').empty();
            if (data.length === 0) {
                $('#sensor-list').append('<li class="list-group-item text-muted">暂无传感器数据</li>');
            } else {
                data.forEach(node => {
                    let label = node.labels[0];
                    let props = Object.entries(node.properties)
                        .map(([key, val]) => `<span class="text-muted">${key}:</span> <strong>${val}</strong>`)
                        .join(", ");
                    
                    let statusClass = node.properties.status === 'active' ? 'status-active' : 'status-inactive';
                    
                    $('#sensor-list').append(`
                        <li class="list-group-item sensor-item">
                            <div class="d-flex justify-content-between">
                                <div>
                                    <span class="badge ${statusClass} status-badge">${node.properties.status}</span>
                                    <span class="fw-bold">${label} ${node.properties.id}</span>
                                </div>
                                <small class="text-muted">${node.properties.type}</small>
                            </div>
                            <div class="mt-2 text-sm">${props}</div>
                        </li>
                    `);
                });
            }
        });
    }

    loadSensors();

    // 添加新的键值对字段
    $('#add-field').click(function() {
        $('#measured-values').append(`
            <div class="value-pair">
                <input type="text" class="form-control key" placeholder="参数名">
                <input type="text" class="form-control value" placeholder="数值">
                <button type="button" class="remove-field btn btn-sm btn-outline-danger"><i class="bi bi-x"></i></button>
            </div>
        `);
    });

    // 删除键值对字段
    $(document).on('click', '.remove-field', function() {
        $(this).parent('.value-pair').remove();
    });

    // 提交传感器信息
    $('#sensor-form').submit(function(event) {
        event.preventDefault();
        showLoading(this);

        let measuredValues = {};
        $('.value-pair').each(function() {
            let key = $(this).find('.key').val();
            let value = $(this).find('.value').val();
            if (key && value) {
                measuredValues[key] = isNaN(value) ? value : parseFloat(value);
            }
        });

        const sensorData = {
            id: $('#id').val(),
            type: $('#type').val(),
            location: $('#location').val(),
            values: measuredValues
        };

        $.ajax({
            url: '/add_sensor',
            type: 'POST',
            contentType: 'application/json',
            data: JSON.stringify(sensorData),
            success: function(response) {
                showAlert('success', '传感器添加成功');
                $('#sensor-form')[0].reset();
                loadSensors();
                loadImage();
            },
            error: function(xhr) {
                showAlert('danger', xhr.responseJSON?.message || '添加失败');
            },
            complete: function() {
                hideLoading('#sensor-form');
            }
        });
    });

    // 提交传感器与边缘节点连接
    $('#link-sensor-form').submit(function(event) {
        event.preventDefault();
        showLoading(this);

        const data = {
            sensor_id: $('#sensor-id').val(),
            edge_id: $('#edge-id').val()
        };
        
        $.ajax({
            url: '/link_sensor_to_edge',
            type: 'POST',
            contentType: 'application/json',
            data: JSON.stringify(data),
            success: function(response) {
                showAlert('success', response.message);
                $('#link-sensor-form')[0].reset();
                loadImage();
            },
            error: function(xhr) {
                showAlert('danger', xhr.responseJSON?.message || '连接失败');
            },
            complete: function() {
                hideLoading('#link-sensor-form');
            }
        });
    });

    // 提交边缘节点与云平台连接
    $('#link-edge-form').submit(function(event) {
        event.preventDefault();
        showLoading(this);

        const data = {
            edge_id: $('#edge-id-cloud').val(),
            cloud_id: $('#cloud-id').val()
        };
        
        $.ajax({
            url: '/link_edge_to_cloud',
            type: 'POST',
            contentType: 'application/json',
            data: JSON.stringify(data),
            success: function(response) {
                showAlert('success', response.message);
                $('#link-edge-form')[0].reset();
                loadImage();
            },
            error: function(xhr) {
                showAlert('danger', xhr.responseJSON?.message || '连接失败');
            },
            complete: function() {
                hideLoading('#link-edge-form');
            }
        });
    });

    // 替代查询表单提交
    $('#substitute-form').submit(function(event) {
        event.preventDefault();
        showLoading(this);

        const sensorId = $('#inactive-id').val();

        $.get(`/get_substitutes/${sensorId}`, function(data) {
            $('#substitute-list').empty();
            if (data.length === 0) {
                $('#substitute-list').append('<li class="list-group-item text-muted">没有找到可替代的传感器</li>');
            } else {
                data.forEach(sensor => {
                    let scoreHtml = sensor.score ? `<span class="badge bg-success float-end">评分: ${sensor.score}</span>` : '';
                    $('#substitute-list').append(`
                        <li class="list-group-item d-flex justify-content-between align-items-center">
                            <div>
                                <span class="fw-bold">${sensor.id}</span>
                                <small class="text-muted d-block">${sensor.type} | ${sensor.location}</small>
                            </div>
                            ${scoreHtml}
                        </li>
                    `);
                });
            }
        }).fail(function() {
            showAlert('danger', '查询失败');
        }).always(function() {
            hideLoading('#substitute-form');
        });
    });
    
    // 自动替换表单提交
    $('#auto-replace-form').submit(function(event) {
        event.preventDefault();
        showLoading(this);

        const sensorId = $('#auto-replace-id').val();
        $('#replace-log').text('正在进行替换...');

        $.post(`/auto_replace/${sensorId}`, function(response) {
            if (response.success) {
                $('#replace-log').html(
                    `<span class="text-success">${response.message}</span><br>` +
                    `<span class="text-muted">替代传感器ID：${response.replacement_id}</span>`
                );
                const imageUrl = `/get_replace_graph?failed_id=${sensorId}&replacement_id=${response.replacement_id}`;
                $('#graph-sub-img').attr('src', imageUrl).show(); 
                loadSensors();
            } else {
                $('#replace-log').html(
                    `<span class="text-danger">${response.message}</span>`
                );
            }
            
        }).fail(function() {
            $('#replace-log').html('<span class="text-danger">请求失败，请检查网络或服务状态。</span>');
        }).always(function() {
            hideLoading('#auto-replace-form');
        });
    });
    //激活传感器
    $('#activate-form').submit(function(event) {
        event.preventDefault(); // 阻止默认提交行为

        const sensorId = $('#activate-id').val().trim();
        $('#activate-result').html('<span class="text-muted">正在激活传感器...</span>');

        $.post(`/activate_sensor/${sensorId}`, function(response) {
            if (response.success) {
                $('#activate-result').html(`<span class="text-success">${response.message}</span>`);
                loadSensors();
            } else {
                $('#activate-result').html(`<span class="text-danger">${response.message}</span>`);
            }
        }).fail(function() {
            $('#activate-result').html('<span class="text-danger">请求失败，请检查网络或服务器状态。</span>');
        });
    });
    // 删除传感器
    $('#delete-form').submit(function(event) {
        event.preventDefault();
        showLoading(this);

        const sensorId = $('#delete-id').val();

        $.ajax({
            url: `/delete_sensor/${sensorId}`,
            type: 'DELETE',
            success: function(response) {
                showAlert('success', `传感器 ${sensorId} 已删除`);
                $('#delete-form')[0].reset();
                loadSensors();
                loadImage();
            },
            error: function(xhr) {
                showAlert('danger', xhr.responseJSON?.message || '删除失败');
            },
            complete: function() {
                hideLoading('#delete-form');
            }
        });
    });
});

function loadImage() {
    $('#graph-img').attr('src', '/graph_image?ts=' + new Date().getTime());
}
function loadSubImage() {
    $('#graph-sub-img').attr('src', '/send_replace_img?ts=' + new Date().getTime());
}
function showAlert(type, message) {
    const alert = $(`
        <div class="alert alert-${type} alert-dismissible fade show" role="alert">
            ${message}
            <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
        </div>
    `);
    $('.container').prepend(alert);
    setTimeout(() => alert.alert('close'), 5000);
}

function showLoading(form) {
    $(form).find('button[type="submit"]').prop('disabled', true);
    $(form).find('button[type="submit"]').html('<span class="spinner-border spinner-border-sm" role="status"></span> 处理中...');
}

function hideLoading(form) {
    $(form).find('button[type="submit"]').prop('disabled', false);
    $(form).find('button[type="submit"]').html(function() {
        const icons = {
            '#sensor-form': 'bi-save',
            '#link-sensor-form': 'bi-plug',
            '#link-edge-form': 'bi-cloud-arrow-up',
            '#substitute-form': 'bi-search',
            '#delete-form': 'bi-trash'
        };
        return `<i class="bi ${icons[form]}"></i> ${$(this).text().replace('处理中...', '').trim()}`;
    });
}